import os
import json
from pathlib import Path
import mwparserfromhell

def get_all_templates(wikitext_json):
    # 1. 加载 JSON 文件
    with open(wikitext_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 2. 定位到 Wikitext 正文 (MediaWiki 标准结构)
    try:
        pages = data.get("query", {}).get("pages", {})
        page_id = list(pages.keys())[0]
        # 获取真正的 Wiki 源码字符串
        wikitext = pages[page_id]['revisions'][0]['slots']['main']['*']
    except (KeyError, IndexError):
        print("JSON 结构不正确，无法找到正文内容")
        wikitext = ""
    
    # 3. 解析 Wikitext
    if wikitext:
        code = mwparserfromhell.parse(wikitext)
        templates = code.filter_templates()
        
        
        print("--- 该页面发现的所有模板清单 ---")
        if not templates:
            print("警告：解析器未发现任何模板。")
        '''
        else:
            for template in templates:
                print(f"模板名称: {template.name.strip()}")
        '''
    
    # 1. 准备数据容器
    all_templates_dict = {}

    # 2. 遍历并整理数据
    for template in code.filter_templates():
        '''
        name = template.name.strip()
        print(f"【模板名】：{name}")
        # 打印该模板下前 3 个参数，看看它是存什么的
        for param in template.params[:3]: 
            print(f"  - {param.name.strip()} = {param.value.strip()[:50]}...") 
        print("-" * 30)
        '''

        t_name = template.name.strip()
        params_data = {param.name.strip(): param.value.strip() for param in template.params}
    
        # 处理同名模板（例如一个页面有多个“天赋”模板）
        if t_name in all_templates_dict:
            # 如果已存在且不是列表，则转为列表存放
            if not isinstance(all_templates_dict[t_name], list):
                all_templates_dict[t_name] = [all_templates_dict[t_name]]
            all_templates_dict[t_name].append(params_data)
        else:
            all_templates_dict[t_name] = params_data

    return all_templates_dict


def write_parsed_json(title, parsed_json):
    # 构造文件名
    file_name = f"test_{title}.json"
    path = Path(f"test/{file_name}")
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
    all_templates_dict = get_all_templates(f"wiki_data/{title}.json")
    write_parsed_json(title, all_templates_dict)


if __name__ == "__main__":
    main()
