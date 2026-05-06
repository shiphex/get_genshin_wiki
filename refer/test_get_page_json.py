import requests
import time
import json
import os
from pathlib import Path

def save_wiki_page_json(title):
    """
    获取指定页面的详细数据并保存为本地 JSON 文件
    """
    api_url = "https://wiki.biligame.com/ys/api.php"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/ys/",  # 告诉服务器你从原神首页跳过来的
    }
    
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvprop": "content", # 获取内容
        "rvslots": "main",   # MediaWiki 新版本需要的参数
        "format": "json"
    }

    response = requests.get(api_url, params=params, headers=headers)
    time.sleep(3)  # 每次请求休息 3 秒
    
    if response.status_code == 200:
        page_json = response.json()
        
        # 额外提示：如何提取正文
        pages = page_json.get("query", {}).get("pages", {})
        for pid in pages:
            content = pages[pid].get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            if content:
                print(f"--- '{title}' 正文预览 (前50字) ---")
                print(content[:50].replace('\n', ' '))
    else:
        print(f"获取失败，状态码: {response.status_code}")

    return page_json


def write_page_json(title, page_json):
    # 构造文件名，例如: ys_角色_list.json
    file_name = f"{title}.json"
    path = Path(f"wiki_data/{file_name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        # indent=4 让 JSON 文件排版整齐，可读性更高
        # ensure_ascii=False 确保中文不变成乱码代码
        json.dump(page_json, f, ensure_ascii=False, indent=4)
        
    print(f"成功保存: {path}")


# --- 测试运行 ---
def main():
    page_json = save_wiki_page_json("哥伦比娅")
    write_page_json("哥伦比娅", page_json)
    page_json = save_wiki_page_json("角斗士的终幕礼")
    write_page_json("角斗士的终幕礼", page_json)


if __name__ == "__main__":
    main()