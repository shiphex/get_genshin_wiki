import os
import json
from pathlib import Path
import mwparserfromhell


def parse_character_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. 定位正文
    pages = data.get("query", {}).get("pages", {})
    page_id = list(pages.keys())[0]
    wikitext = pages[page_id]['revisions'][0]['slots']['main']['*']

    # 2. 使用 mwparserfromhell 解析
    code = mwparserfromhell.parse(wikitext)
    
    # 3. 寻找“角色属性”模板
    character_data = {}
    for template in code.filter_templates():
        # 匹配模板名称（忽略大小写和空格）
        if template.name.matches("角色属性") or "角色" in template.name.strip():
            for param in template.params:
                key = param.name.strip()
                value = param.value.strip()
                character_data[key] = value
    
    return character_data


def write_parsed_json(title, parsed_json):
    # 构造文件名
    file_name = f"parsed_json_{title}.json"
    path = Path(f"parsed_json/{file_name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        # indent=4 让 JSON 文件排版整齐，可读性更高
        # ensure_ascii=False 确保中文不变成乱码代码
        json.dump(parsed_json, f, ensure_ascii=False, indent=4)
        
    print(f"成功保存至: {path}")


# 使用示例
def main():
    filename = "哥伦比娅.json"
    title = os.path.splitext(filename)[0]
    stats = parse_character_json(f"wiki_data/{title}.json")
    write_parsed_json(title, stats)


if __name__ == "__main__":
    main()
