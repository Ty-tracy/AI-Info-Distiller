import os
import requests
import feedparser
from openai import OpenAI
from datetime import datetime, timedelta
import time
from email.utils import parsedate_to_datetime

# ==========================================
# 1. 核心环境配置 (API 密钥)
# ==========================================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# ==========================================
# 2. 终极信息源矩阵 (RSS 订阅源)
# ==========================================
# 📢 [用户自定义区]：国内政策与发改相关源
# 提示：如果你想抓取特定的发改委政策，可以使用 RSSHub 生成（例如 https://rsshub.app/gov/ndrc/zcfb）
DOMESTIC_FEEDS = [
    "https://rsshub.app/gov/ndrc/zcfb",        # 示例：国家发改委-政策发布
    "https://rsshub.app/gov/mof/gzdt",         # 示例：财政部-工作动态
    "https://rsshub.app/21jingji/recommend"    # 示例：21世纪经济报道（偏宏观财经）
]

# 📢 [用户自定义区]：国际宏观与行业视野
INTL_FEEDS = [
    "https://www.economist.com/finance-and-economics/rss.xml", # 经济学人-财经
    "https://hnrss.org/frontpage"                             # 极客论坛（可选，了解前沿科技）
]

# 📢 [用户自定义区]：自定义你的周报名称和你的专属身份/格言
REPORT_TITLE = "📊 专属【宏观政策与发改动态情报】"
REPORT_SUBTITLE = "由 DeepSeek 驱动，聚焦中央预算、国债、专项债及‘六张网’前沿政策动向。"

# ==========================================
# 3. 抓取近期更新的 RSS 文章
# ==========================================
def fetch_recent_rss(feed_urls, days_limit=7):
    print(f"📡 正在扫描订阅源，严格筛选过去 {days_limit} 天内的文章...")
    recent_items = []
    limit_date = datetime.now() - timedelta(days=days_limit)
    
    for url in feed_urls:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.title if hasattr(feed.feed, 'title') else "精选智库"
            
            for entry in feed.entries:
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'published'):
                        pub_date = parsedate_to_datetime(entry.published).replace(tzinfo=None)
                    else:
                        continue
                        
                    if pub_date >= limit_date:
                        recent_items.append({
                            "title": entry.title,
                            "url": entry.link,
                            "summary": entry.get("summary", ""),
                            "source": source_name,
                            "pub_date": pub_date
                        })
                except Exception:
                    pass
        except Exception as e:
            print(f"解析 {url} 失败: {e}")
            
    recent_items.sort(key=lambda x: x['pub_date'], reverse=True)
    print(f"✅ 扫描完毕，共发现 {len(recent_items)} 篇新鲜文章。")
    return recent_items

# ==========================================
# 4. Jina 穿透抓取正文
# ==========================================
def extract_full_text(url):
    jina_url = f"https://r.jina.ai/{url}"
    try:
        response = requests.get(jina_url, timeout=15)
        if response.status_code == 200:
            text = response.text
            if len(text) > 200 and "Access Denied" not in text:
                return text[:3800] 
    except Exception:
        pass
    return "抓取正文受限，请基于标题和摘要进行研判。"

# ==========================================
# 5. DeepSeek 深度剖析 (发改专属定制)
# ==========================================
def analyze_with_deepseek(title, content, source_name):
    # 📢 这里的提示词已经为你量身定制，重点针对宏观政策与项目投向
    prompt = f"""
    你是一位资深的发改委宏观政策研究员与项目谋划专家，擅长从繁杂的政务资讯中过滤噪音，提取对地方发改工作有指导价值的核心信息。
    请审读这篇来自【{source_name}】的最新资讯：
    【标题】：{title}
    【正文/摘要】：{content}
    
    【判定准则】
    1. 如果该内容完全是无营养的会议流水账、纯广告、或与宏观经济、项目建设、财政政策毫无关系，请仅回复“无效资讯”。
    2. 如果内容具备信息增量，请发挥你的专长，按以下结构输出结构化简报。

    【深度洞察产出】
    📰 **1. 政策核心**：用 1-2 句话极简概括政策的核心事实（发布了什么资金计划、聚焦哪些领域、提出了什么新要求）。
    🧠 **2. 发改视角**：分析该政策背后的底层逻辑。重点解读其对“中央预算内投资”、“超长期特别国债”、“地方政府专项债”或“六张网”等重大基础设施/产业方向的影响。
    🎯 **3. 谋划建议**：结合该资讯，给地方发改部门提供一个具体的项目谋划或资金争取的实操建议。
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个能提供高信噪比政策摘要的顶级政务与宏观分析助理。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI 分析失败: {e}")
        return "无效资讯"

# ==========================================
# 6. 流水线核心逻辑
# ==========================================
def process_news_pipeline(news_list, section_title, limit=None):
    report_text = f"## {section_title}\n\n"
    valid_count = 0
    
    for item in news_list:
        if limit is not None and valid_count >= limit:
            print(f"🛑 {section_title} 已达到 {limit} 篇上限，停止分析。")
            break
            
        print(f"🧐 评估文章: {item['title'][:30]}... (发布于 {item['pub_date'].strftime('%m-%d')})")
        full_text = extract_full_text(item['url'])
        time.sleep(1.5) # 防止请求过频被封
        
        analysis = analyze_with_deepseek(item['title'], full_text, item['source'])
        
        if "无效资讯" not in analysis:
            valid_count += 1
            report_text += f"### {valid_count}. {item['title']}\n"
            report_text += f"🔗 **原文直达**：[点击阅读全文]({item['url']})\n\n"
            report_text += f"{analysis}\n\n---\n\n"
            
    if valid_count == 0:
        report_text += "> 🛡️ *本周期内暂无符合价值研判标准的新鲜动态。*\n\n---\n\n"
    return report_text

# ==========================================
# 7. 执行与微信推送
# ==========================================
if __name__ == "__main__":
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    raw_domestic = fetch_recent_rss(DOMESTIC_FEEDS)
    raw_intl = fetch_recent_rss(INTL_FEEDS)
    
    # 构建报告头部
    final_report = f"# {REPORT_TITLE}\n\n"
    final_report += f"> 📅 **生成日期**：{today_str}\n"
    final_report += f"> 💡 **订阅说明**：{REPORT_SUBTITLE}\n\n---\n\n"
    
    # 建议一开始把 limit 设小一点，比如国内 3 篇，国际 2 篇，跑通后再增加
    final_report += process_news_pipeline(raw_domestic, "📌 第一部分：国内宏观政策动态", limit=3)
    final_report += process_news_pipeline(raw_intl, "🌐 第二部分：国际视野与行业观察", limit=2)
    
    # 【防超长截断保护】如果文章太长超过 1.8 万字，自动截断防止推送失败
    if len(final_report) > 18000:
        final_report = final_report[:18000] + "\n\n> ⚠️ *报告内容过长，已自动截断。*"

    # 推送至微信 (使用 txt 模板防止格式被拦截，并打印真实返回结果)
    try:
        print("📡 正在推送到 PushPlus...")
        response = requests.post("https://www.pushplus.plus/send", json={
            "token": PUSHPLUS_TOKEN,
            "title": f"【每周宏观】{REPORT_TITLE} - {today_str}",
            "content": final_report,
            "template": "txt" 
        }, timeout=15)
        
        # 打印服务器的真实回复！
        print(f"📡 PushPlus 服务器真实回复: {response.text}")
        
        if response.status_code == 200 and '"code":200' in response.text:
            print("✅ 微信推送成功！请去公众号查看。")
        else:
            print("❌ 微信推送失败！请检查上方服务器返回的错误码（如：905代表未实名）。")
            
    except Exception as e:
        print(f"❌ 网络请求异常: {e}")
