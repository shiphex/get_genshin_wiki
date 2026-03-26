"""日志配置模块"""
import logging
import sys


def setup_logging(level: str = "INFO", format_str: str = None) -> None:
    """配置日志

    Args:
        level: 日志级别
        format_str: 日志格式
    """
    if format_str is None:
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
