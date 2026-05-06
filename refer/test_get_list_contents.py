import requests
import time
import json
from pathlib import Path

def get_category_members(category_name):
    api_url = "https://wiki.biligame.com/ys/api.php"
    titles = []
    cmcontinue = None
    
    # 核心修复：添加 User-Agent 模拟浏览器
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://wiki.biligame.com/ys/",  # 告诉服务器你从原神首页跳过来的
    "Accept": "application/json, text/javascript, */*; q=0.01"
    }
    
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category_name}",
            "cmlimit": "max",
            "format": "json",
            "cmcontinue": cmcontinue
        }
        
        response = requests.get(api_url, params=params, headers=headers)
        time.sleep(3)  # 每次请求休息 3 秒
        
        # 调试用：如果报错，打印出服务器到底返回了什么
        if response.status_code != 200:
            print(f"请求失败，状态码：{response.status_code}")
            break
            
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            print("服务器返回了非 JSON 内容，前 100 个字符如下：")
            print(response.text[:100]) # 看看是不是返回了 HTML 报错页
            break
        
        if 'query' in data:
            for item in data['query']['categorymembers']:
                titles.append(item['title'])
        
        if 'continue' in data:
            cmcontinue = data['continue']['cmcontinue']
        else:
            break
            
    return titles


def write_list_json(role_list, category):
    # 构造文件名，例如: ys_角色_list.json
    file_name = f"ys_{category}_list.json"
    path = Path(f"list/{file_name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        # indent=4 让 JSON 文件排版整齐，可读性更高
        # ensure_ascii=False 确保中文不变成乱码代码
        json.dump(role_list, f, ensure_ascii=False, indent=4)
        
    print(f"成功获取 {len(role_list)} 个条目，并已保存至: {path}")


# 运行测试
def main():
    crawl_category = ["活动任务"]
    '''
    ["世界任务", "主线", "任务", 
    "传说任务", "多重系列任务", "委托任务",
    "天赋培养素材", "活动系列任务", "活动任务",
    "系列任务", "隐藏任务", "魔神任务",
    "武器强化素材", "武器突破素材", "圣遗物强化素材"]
    '''
    
    '''
    ["角色", "武器", "圣遗物套装", 
     "食物", "任务道具", "冒险道具", 
     "材料", "活动材料", "精炼材料",
     "书籍", "怪物", "野生生物", "动物", 
     "NPC", "北陆图书馆"]  # , "提瓦特编年史（公元纪）"]
    '''
    
    for category in crawl_category:
        try:
            role_list = get_category_members(category)
            write_list_json(role_list, category)
        except Exception as e:
            print(f"运行出错: {e}")


if __name__ == "__main__":
    main()