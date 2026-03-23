"""MediaWiki API client for fetching pages."""

import logging
import time
from typing import Any, Dict, Generator, Iterator, Optional

import requests

from ..schema.models import PageListItem, Revision, WikiPage
from ..utils.config import Config
from ..utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class MediaWikiError(Exception):
    """Base exception for MediaWiki errors."""
    pass


class MediaWikiAPIError(MediaWikiError):
    """Exception for MediaWiki API errors."""

    def __init__(self, code: str, info: str):
        self.code = code
        self.info = info
        super().__init__(f"API error {code}: {info}")


class MediaWikiClient:
    """Client for interacting with MediaWiki API."""

    def __init__(self, config: Config):
        """
        Initialize MediaWiki client.

        Args:
            config: Configuration object
        """
        self.config = config
        self.api_url = config.api_url
        self.base_url = config.base_url
        self.timeout = config.timeout
        self.max_retries = config.max_retries
        self.user_agent = config.user_agent
        self.limit_per_request = config.limit_per_request

        self.session = requests.Session()
        # Clear any system proxy settings to avoid connection issues
        self.session.trust_env = False
        self.session.proxies = {
            "http": None,
            "https": None,
        }
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://wiki.biligame.com/ys/",
        })

        self.rate_limiter = RateLimiter(interval=config.request_interval)

        self._continue_params: Dict[str, Any] = {}

    def _request(
        self,
        params: Dict[str, Any],
        retries: int = 0,
    ) -> Dict[str, Any]:
        """
        Make API request with retry logic.

        Args:
            params: API parameters
            retries: Current retry count

        Returns:
            API response as dictionary

        Raises:
            MediaWikiAPIError: If API returns an error
            MediaWikiError: For other errors
        """
        # Apply rate limiting
        self.rate_limiter.wait()

        try:
            response = self.session.get(
                self.api_url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()

            # Check for API errors
            if "error" in data:
                error = data["error"]
                raise MediaWikiAPIError(error.get("code", "unknown"), error.get("info", ""))

            return data

        except requests.exceptions.Timeout as e:
            logger.warning(f"Request timeout: {e}")
            if retries < self.max_retries:
                return self._request(params, retries + 1)
            raise MediaWikiError(f"Request timeout after {self.max_retries} retries") from e

        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                status_code = e.response.status_code
                # Handle rate limiting (429) and server errors (5xx)
                # Also handle Bilibili's custom 567 error
                if status_code == 429 or status_code >= 500 or status_code == 567:
                    logger.warning(f"HTTP {status_code}, retrying...")
                    if retries < self.max_retries:
                        # Exponential backoff
                        sleep_time = 2 ** retries * 5
                        time.sleep(sleep_time)
                        return self._request(params, retries + 1)
            raise MediaWikiError(f"HTTP error: {e}") from e

        except requests.exceptions.RequestException as e:
            if retries < self.max_retries:
                logger.warning(f"Request failed: {e}, retrying...")
                time.sleep(2 ** retries * 5)
                return self._request(params, retries + 1)
            raise MediaWikiError(f"Request failed after {self.max_retries} retries") from e

        except ValueError as e:
            raise MediaWikiError(f"JSON decode error: {e}") from e

    def _build_params(self, action: str, **kwargs) -> Dict[str, Any]:
        """Build API request parameters."""
        params = {
            "action": action,
            "format": "json",
            **kwargs,
        }
        return params

    def get_page(
        self,
        titles: Optional[str | list[str]] = None,
        pageids: Optional[int | list[int]] = None,
        revisions: bool = True,
        parse: bool = False,
    ) -> Iterator[WikiPage]:
        """
        Get page(s) by title or page ID.

        Args:
            titles: Page title(s)
            pageids: Page ID(s)
            revisions: Whether to fetch revisions
            parse: Whether to fetch parsed content

        Yields:
            WikiPage objects
        """
        params = self._build_params(
            "query",
            titles=titles,
            pageids=pageids,
            prop="info|categories|links|templates|revisions" if revisions else "info|categories|links|templates",
        )

        # Limit revision content to reduce API load
        if revisions:
            params["rvprop"] = "ids|timestamp|user|comment|content"

        if parse:
            params["prop"] += "|parse"

        while True:
            data = self._request(params)
            pages = data.get("query", {}).get("pages", {})

            for page_data in pages.values():
                if "missing" in page_data:
                    logger.warning(f"Page not found: {page_data.get('title', pageids)}")
                    continue

                yield self._parse_page_info(page_data)

            # Handle continuation
            continue_param = data.get("continue")
            if continue_param:
                self._continue_params = continue_param
                params.update(continue_param)
            else:
                break

    def _parse_page_info(self, page_data: Dict) -> WikiPage:
        """Parse page info into WikiPage object."""
        page_id = page_data.get("pageid", 0)
        title = page_data.get("title", "")
        namespace = page_data.get("ns", 0)
        last_modified = page_data.get("touched")

        # Build URL
        url = f"{self.base_url}{title.replace(' ', '_')}"

        # Get content
        content_raw = ""
        revision = None
        if "revisions" in page_data:
            revisions = page_data["revisions"]
            if revisions:
                rev = revisions[0]
                content_raw = rev.get("*", "")
                revision = Revision(
                    rev_id=rev.get("revid", 0),
                    parent_id=rev.get("parentid", 0),
                    timestamp=rev.get("timestamp", ""),
                    user=rev.get("user", ""),
                    content_model=rev.get("contentmodel", ""),
                    content_format=rev.get("contentformat", ""),
                    comment=rev.get("comment"),
                )

        # Categories
        categories = [
            cat.get("title", "").replace("Category:", "")
            for cat in page_data.get("categories", [])
        ]

        # Links
        links = [
            link.get("title", "")
            for link in page_data.get("links", [])
        ]

        # Templates
        templates = [
            tmpl.get("title", "")
            for tmpl in page_data.get("templates", [])
        ]

        return WikiPage(
            id=page_id,
            title=title,
            url=url,
            namespace=namespace,
            content_raw=content_raw,
            revision=revision,
            categories=categories,
            links=links,
            templates=templates,
            page_id=page_id,
            last_modified=last_modified,
        )

    def get_category_members(
        self,
        category: str,
        cmtitle: Optional[str] = None,
        cmtype: str = "page",
    ) -> Iterator[PageListItem]:
        """
        Get members of a category.

        Args:
            category: Category name (without "Category:" prefix)
            cmtitle: Full category title (including prefix)
            cmtype: Member type: "page", "subcat", "file"

        Yields:
            PageListItem objects
        """
        if cmtitle is None:
            cmtitle = f"Category:{category}"

        params = self._build_params(
            "query",
            list="categorymembers",
            cmtitle=cmtitle,
            cmtype=cmtype,
            cmlimit=self.limit_per_request,
        )

        while True:
            data = self._request(params)
            members = data.get("query", {}).get("categorymembers", [])

            for member in members:
                yield PageListItem(
                    page_id=member.get("pageid", 0),
                    title=member.get("title", ""),
                    namespace=member.get("ns", 0),
                    redirect=member.get("redirect", False),
                )

            # Handle continuation
            continue_param = data.get("continue")
            if continue_param:
                self._continue_params = continue_param
                params.update(continue_param)
            else:
                break

    def get_all_categories(self, limit: Optional[int] = None) -> Iterator[str]:
        """
        Get all categories.

        Args:
            limit: Maximum number of categories to fetch

        Yields:
            Category titles
        """
        params = self._build_params(
            "query",
            list="allcategories",
            aclimit=self.limit_per_request,
        )

        count = 0
        while True:
            if limit and count >= limit:
                break

            data = self._request(params)
            categories = data.get("query", {}).get("allcategories", [])

            for cat in categories:
                yield cat.get("*", "")
                count += 1
                if limit and count >= limit:
                    break

            # Handle continuation
            continue_param = data.get("continue")
            if continue_param:
                self._continue_params = continue_param
                params.update(continue_param)
            else:
                break

    def get_recent_changes(
        self,
        rcstart: Optional[str] = None,
        rcend: Optional[str] = None,
        rclimit: int = 500,
    ) -> Iterator[Dict]:
        """
        Get recent changes.

        Args:
            rcstart: Start timestamp
            rcend: End timestamp
            rclimit: Number of changes to fetch

        Yields:
            Change dictionaries
        """
        params = self._build_params(
            "query",
            list="recentchanges",
            rcstart=rcstart,
            rcend=rcend,
            rclimit=min(rclimit, self.limit_per_request),
            rcprop="title|ids|timestamp|user|comment|parsedcomment|redirect|title",
        )

        while True:
            data = self._request(params)
            changes = data.get("query", {}).get("recentchanges", [])

            for change in changes:
                yield change

            # Handle continuation
            continue_param = data.get("continue")
            if continue_param:
                self._continue_params = continue_param
                params.update(continue_param)
            else:
                break

    def search(
        self,
        query: str,
        limit: int = 50,
        namespace: int = 0,
    ) -> Iterator[PageListItem]:
        """
        Search for pages.

        Args:
            query: Search query
            limit: Maximum results
            namespace: Namespace to search in

        Yields:
            PageListItem objects
        """
        params = self._build_params(
            "query",
            list="search",
            srsearch=query,
            srlimit=min(limit, self.limit_per_request),
            srnamespace=namespace,
        )

        while True:
            data = self._request(params)
            results = data.get("query", {}).get("search", [])

            for result in results:
                yield PageListItem(
                    page_id=result.get("pageid", 0),
                    title=result.get("title", ""),
                    namespace=result.get("ns", 0),
                )

            # Handle continuation
            continue_param = data.get("continue")
            if continue_param:
                self._continue_params = continue_param
                params.update(continue_param)
            else:
                break

    def get_page_html(self, title: str) -> str:
        """
        Get rendered HTML for a page.

        Args:
            title: Page title

        Returns:
            HTML content
        """
        params = {
            "action": "parse",
            "page": title,
            "format": "json",
            "prop": "text",
        }

        data = self._request(params)
        parse_result = data.get("parse", {})
        text = parse_result.get("text", {})
        return text.get("*", "")

    def reset_continue(self) -> None:
        """Reset continuation parameters."""
        self._continue_params = {}
