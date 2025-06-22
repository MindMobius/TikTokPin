# main.py

import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv

# --- 配置区 ---
USER_FILE = 'user.txt'
LOGS_DIR = 'logs'
VIDEO_COUNT = 10  # 定义要抓取前多少个视频

# --- 辅助函数：从 TikTok 视频 ID 中提取发布时间 ---
def extract_timestamp_from_id(video_id: str) -> datetime:
    """从视频ID中提取UNIX时间戳并转换为datetime对象"""
    try:
        video_id_int = int(video_id)
        timestamp = video_id_int >> 32
        return datetime.fromtimestamp(timestamp)
    except (ValueError, TypeError):
        return None

# --- 主函数 ---
def main():
    load_dotenv()

    print("--- TikTok 用户主页监控脚本启动 ---")
    print("--- 模式: 有头模式 (将显示浏览器窗口以便调试) ---")

    if not os.path.exists(USER_FILE):
        print(f"错误: 未找到用户列表文件 '{USER_FILE}'。")
        with open(USER_FILE, 'w', encoding='utf-8') as f:
            f.write("tiktok\n")
            f.write("budgebuys\n")
        print(f"已为您创建示例文件 '{USER_FILE}'，请填入您想监控的用户名后重新运行。")
        return

    with open(USER_FILE, 'r', encoding='utf-8') as f:
        usernames = [line.strip() for line in f if line.strip()]

    if not usernames:
        print("用户列表为空，脚本退出。")
        return

    print(f"成功读取 {len(usernames)} 个用户。")

    with sync_playwright() as p:
        launch_options = {
            "headless": False,
            "slow_mo": 50
        }
        proxy_server = os.getenv('HTTP_PROXY')
        if proxy_server:
            print(f"[INFO] 检测到代理配置，将使用代理: {proxy_server}")
            launch_options["proxy"] = {"server": proxy_server}
        else:
            print("[INFO] 未配置代理，将直接连接。")
        
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        page = context.new_page()

        for username in usernames:
            print(f"\n[INFO] ----------------------------------------")
            print(f"[INFO] 正在监控用户: {username}")
            
            url = f"https://www.tiktok.com/@{username}"
            
            try:
                print(f"[DEBUG] 步骤 1: 正在导航到页面 -> {url}")
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                print("[DEBUG] 步骤 2: 页面导航初步完成。")

                video_list_selector = '[data-e2e="user-post-item-list"]'
                print(f"[DEBUG] 步骤 3: 正在等待关键元素(视频列表)出现...")
                page.wait_for_selector(video_list_selector, timeout=30000)
                print("[DEBUG] 步骤 4: 关键元素已成功加载。")

                # --- 调整：获取用户信息 (用户名和昵称) ---
                print("[DEBUG] 步骤 5: 正在获取用户信息...")
                
                # 获取昵称 (使用 data-e2e="user-subtitle")
                nickname = "N/A"
                nickname_selector = '[data-e2e="user-subtitle"]'
                nickname_element = page.query_selector(nickname_selector)
                if nickname_element:
                    nickname = nickname_element.inner_text().strip()
                    print(f"[DEBUG] 成功获取昵称: {nickname}")
                else:
                    print("[WARN] 未找到用户昵称元素。")

                # 获取并验证页面上的用户名 (使用 data-e2e="user-title")
                username_on_page_selector = '[data-e2e="user-title"]'
                username_on_page_element = page.query_selector(username_on_page_selector)
                if username_on_page_element:
                    username_on_page = username_on_page_element.inner_text().strip()
                    print(f"[DEBUG] 成功获取页面用户名: {username_on_page}")
                    # 验证用户名是否匹配
                    if f"@{username}" != username_on_page:
                        print(f"[CRITICAL WARN] 页面显示的用户名 '{username_on_page}' 与期望的 '{username}' 不匹配！可能页面已重定向或出错。")
                else:
                    print("[WARN] 未找到页面用户名元素，无法验证。")
                
                # --- 获取视频元素 ---
                print("[DEBUG] 步骤 6: 正在抓取所有视频元素...")
                video_elements = page.query_selector_all('[data-e2e="user-post-item"]')
                
                if not video_elements:
                    print(f"[WARN] 用户 '{username}' 的主页上没有找到视频。")
                    continue

                print(f"找到 {len(video_elements)} 个视频，将处理前 {VIDEO_COUNT} 个。")
                
                all_videos_data = []
                for i, video_element in enumerate(video_elements[:VIDEO_COUNT]):
                    try:
                        video_data = {
                            "publish_time": "N/A", "views": "N/A", "url": "N/A", "is_pinned": "否"
                        }

                        pinned_element = video_element.query_selector('[data-e2e="video-card-pinned"]')
                        if pinned_element:
                            video_data["is_pinned"] = "是"

                        link_element = video_element.query_selector('a')
                        if link_element:
                            video_url = link_element.get_attribute('href')
                            video_data["url"] = video_url
                            
                            video_id = video_url.split('/video/')[-1].split('?')[0] # 清理URL参数
                            publish_datetime = extract_timestamp_from_id(video_id)
                            if publish_datetime:
                                video_data["publish_time"] = publish_datetime.strftime('%Y-%m-%d %H:%M:%S')

                        views_element = video_element.query_selector('[data-e2e="video-views"]')
                        if views_element:
                            video_data["views"] = views_element.inner_text()
                        
                        all_videos_data.append(video_data)
                    
                    except Exception as e:
                        print(f"  - 处理第 {i+1} 个视频时出错: {e}")

                if all_videos_data:
                    last_update_time = "未知"
                    # 寻找第一个非置顶视频的发布时间作为最新更新时间
                    for video in all_videos_data:
                        if video['is_pinned'] == '否' and video['publish_time'] != "N/A":
                            last_update_time = video['publish_time']
                            break
                    # 如果所有视频都是置顶或无法获取时间，则退回使用第一个视频的时间
                    if last_update_time == "未知" and all_videos_data[0]['publish_time'] != "N/A":
                        last_update_time = all_videos_data[0]['publish_time']

                    user_log_dir = os.path.join(LOGS_DIR, username)
                    os.makedirs(user_log_dir, exist_ok=True)
                    timestamp_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                    file_path = os.path.join(user_log_dir, f"{timestamp_str}.txt")
                    
                    with open(file_path, 'w', encoding='utf-8') as log_file:
                        log_file.write(f"用户账号: @{username}\n")
                        log_file.write(f"用户昵称: {nickname}\n")
                        log_file.write(f"最新更新: {last_update_time}\n")
                        log_file.write(f"记录时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        log_file.write(f"----------------------------------------\n\n")
                        
                        for idx, data in enumerate(all_videos_data):
                            log_file.write(f"--- 视频 {idx+1} ---\n")
                            log_file.write(f"是否置顶: {data['is_pinned']}\n")
                            log_file.write(f"发布时间: {data['publish_time']}\n")
                            log_file.write(f"播放量: {data['views']}\n")
                            log_file.write(f"视频地址: {data['url']}\n\n")
                    
                    print(f"[SUCCESS] 用户 '{username}' 的数据已成功保存到: {file_path}")
                else:
                    print(f"[WARN] 未能为用户 '{username}' 抓取到任何视频数据。")

            except PlaywrightTimeoutError:
                print(f"[ERROR] 处理用户 '{username}' 时发生超时错误！")
                print("      请检查弹出的浏览器窗口，确认是否需要人机验证、登录或存在其他页面问题。")
                input("      请观察浏览器窗口，排查问题后按 Enter 键继续处理下一个用户...")
            except Exception as e:
                print(f"[ERROR] 处理用户 '{username}' 时发生未知错误: {e}")

        context.close()
        browser.close()
        print("\n--- 所有用户处理完毕，脚本结束 ---")

if __name__ == "__main__":
    main()