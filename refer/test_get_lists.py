import requests
import json
from pathlib import Path

def explore_wiki_categories(keyword=None):
    """
    探测 Wiki 中的分类列表
    keyword: 如果指定，则只搜索包含该词的分类（如 "圣遗物"）
    """
    api_url = "https://wiki.biligame.com/ys/api.php"
    
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://wiki.biligame.com/ys/",  # 告诉服务器你从原神首页跳过来的
    "Accept": "application/json, text/javascript, */*; q=0.01"
    }
    
    # 如果有关键词，使用 acprefix 进行前缀匹配；否则列出全站分类
    params = {
        "action": "query",
        "list": "allcategories",
        "aclimit": "max",
        "format": "json"
    }
    if keyword:
        params["acprefix"] = keyword

    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        
        # 核心调试：如果还是报错，打印出状态码和前几个字符
        if response.status_code != 200:
            print(f"探测失败！状态码：{response.status_code}")
            return []

        data = response.json()
        categories = [item['*'] for item in data.get('query', {}).get('allcategories', [])]
        return categories

    except Exception as e:
        print(f"发生错误: {e}")
        return []



# --- 执行探测 ---
def main():
    print("正在探测全站顶级分类，请稍候...")
    all_cats = explore_wiki_categories()

    if all_cats:
        # 保存探测结果
        path = Path("list/wiki_all_categories.json")
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_cats, f, ensure_ascii=False, indent=4)

        print(f"探测完成！共发现 {len(all_cats)} 个分类。")
        print(f"结果已保存至：{path}")

    '''    
        # 针对你关心的“圣遗物”进行专项探测
        print("\n--- 圣遗物专项探测 ---")
        syw_cats = explore_wiki_categories("圣遗物")
        print(f"包含'圣遗物'关键词的分类有：{syw_cats}")
    else:
        print("未能获取到分类，请检查网络或 api_url 是否准确。")
    '''


if __name__ == "__main__":
    main()