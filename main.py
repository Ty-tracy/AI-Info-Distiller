import os
import sys
import requests
import feedparser
from openai import OpenAI
from datetime import datetime, timedelta
import time
from email.utils import parsedate_to_datetime

# ==========================================
# 1. 核心配置
# ==========================================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# ==========================================
# 2. 你的定制化信息源矩阵 (宏观政策已替换为 Google News 方案)
# ==========================================
TARGET_TOPIC = sys.argv[1] if len(sys.argv) > 1 else "宏观政策"

FEEDS_CONFIG = {
    "宏观政策": {
        "title": "🏛️ 宏观政策观察窗口",
        "prompt_role": "你是一位资深的宏观政策研究员。请重点关注政策释放的资金信号、产业导向和改革方向。",
        "urls": [
            # 使用 Google News 搜索：限定 gov.cn 的“政策”栏目，过去7天
            "https://news.google.com/rss/search?q=site:gov.cn/zhengce+when:7d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            # 限定社科院网站，过去7天
            "https://news.google.com/rss/search?q=site:casssp.cssn.cn+when:7d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        ]
    },
    "观点与实践": {
        "title": "🧠 智库观点与实践观察",
        "prompt_role": "你是一位智库分析师。请重点提炼文章的理论深度、底层逻辑，以及对地方经济实践的启发。",
        "urls": [
            "https://rsshub.rssforever.com/chinathinktanks/6",
            "https://rsshub.rssforever.com/chinathinktanks/3",
            "https://rsshub.rssforever.com/chinathinktanks/10",
            "https://rsshub.rssforever.com/chinathinktanks/131"
        ]
    },
    "财经洞察": {
        "title": "📈 财经与投资洞察",
        "prompt_role": "你是一位首席经济学家。请重点关注金融市场波动、行业研究报告的核心结论和宏观经济指标。",
        "urls": [
            "https://rsshub.rssforever.com/nifd/research/3333d2af-91d6-429b-be83-28b92f31b6d7",
            "https://rsshub.rssforever.com/mckinsey/cn",
            "https://rsshub.rssforever.com/dtcj/datainsight"
        ]
    },
    "社会情绪": {
        "title": "🔥 社会情绪与舆情观察",
        "prompt_role": "你是一位敏锐的社会观察员。请过滤掉纯娱乐八卦，重点分析老百姓在关心什么、焦虑什么、期待什么，反映了怎样的社会心理。",
        "urls": [
            "https://zhihu-hot.ayanamist.com/feed.xml",
            "https://rsshub.rssforever.com/weibo/search/hot"
        ]
    },
    "娱乐解压": {
        "title": "🎬 娱乐与文化解压",
        "prompt_role": "你是一位资深文娱主编。请用轻松幽默的语气，推荐值得一看的影视剧、UP主视频或娱乐热点。",
        "urls": [
            "https://rsshub.rssforever.com/bilibili/weekly",
            "https://rsshub.rssforever.com/douban/celebrity/1274261"
        ]
    }
}

# 获取当前主题的配置
current_config = FEEDS_CONFIG.get(TARGET_TOPIC, FEEDS_CONFIG["宏观政策"])
CURRENT_FEEDS = current_config["urls"]
REPORT_TITLE = current_config["title"]
AI_ROLE = current_config["prompt_role"]


# ==========================================
# 3. 抓取与解析
# ==========================================
def fetch_recent_rss(feed_urls, days_limit=7):
    print(f"📡 正在扫描【{TARGET_TOPIC}】源，筛选过去 {days_limit} 天内的文章...")
    recent_items = []
    limit_date = datetime.now() - timedelta(days=days_limit)
    
    for url in feed_urls:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.title if hasattr(feed.feed, 'title') else "精选智库"
            
            for entry in feed.entries:
                try:
                    pub_date = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'published'):
                        pub_date = parsedate_to_datetime(entry.published).replace(tzinfo=None)
                        
                    # 放宽条件：如果没有时间，或者时间在7天内，都收进来
                    if pub_date is None or pub_date >= limit_date:
                        recent_items.append({
                            "title": entry.title,
                            "url": entry.link,
                            "summary": entry.get("summary", ""),
                            "source": source_name,
                            "pub_date": pub_date if pub_date else datetime.now()
                        })
                except Exception:
                    pass
        except Exception as e:
            print(f"解析 {url} 失败: {e}")
            
    recent_items.sort(key=lambda x: x['pub_date'], reverse=True)
    print(f"✅ 扫描完毕，共发现 {len(recent_items)} 篇新鲜文章。")
    return recent_items

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
# 4. AI 动态分析
# ==========================================
def analyze_with_deepseek(title, content, source_name):
    prompt = f"""
    {AI_ROLE}
    请审读这篇来自【{source_name}】的最新资讯：
    【标题】：{title}
    【正文/摘要】：{content}
    
    【判定准则】
    1. 如果该内容完全是无营养的广告、纯软文、毫无逻辑的碎片信息（对于社会情绪频道，纯明星八卦视为无效），请仅回复“无效资讯”。
    2. 如果内容具备信息增量或阅读价值，请发挥你的专长，按以下结构输出结构化简报：

    【深度洞察产出】
    📰 **1. 核心提要**：用 1-2 句话极简概括这篇资讯的核心事实。
    🧠 **2. 深度洞察**：结合你当前扮演的角色（政策研究员/智库分析师/经济学家/社会观察员），深入分析背后的逻辑或趋势。
    🎯 **3. 行动启发**：给读者提供一个具体的思考角度或落地的行动建议。
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个高信噪比的情报提炼专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI 分析出错: {e}")
        return "无效资讯"

# ==========================================
# 5. 流水线与推送
# ==========================================
def process_news_pipeline(news_list, limit=4):
    report_text = ""
    valid_count = 0
    
    for item in news_list:
        if valid_count >= limit:
            print(f"🛑 已达到 {limit} 篇上限，停止分析。")
            break
            
        print(f"🧐 评估: {item['title'][:30]}...")
        full_text = extract_full_text(item['url'])
        time.sleep(1.5) 
        
        analysis = analyze_with_deepseek(item['title'], full_text, item['source'])
        
        if "无效资讯" not in analysis:
            valid_count += 1
            report_text += f"### {valid_count}. {item['title']}\n"
            report_text += f"🔗 **原文直达**：[点击阅读全文]({item['url']})\n\n"
            report_text += f"{analysis}\n\n---\n\n"
            
    if valid_count == 0:
        report_text += "> 🛡️ *本周期内暂无符合价值研判标准的新鲜动态。*\n\n"
    return report_text

if __name__ == "__main__":
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    print(f"🚀 开始生成【{TARGET_TOPIC}】报告...")
    raw_news = fetch_recent_rss(CURRENT_FEEDS)
    
    final_report = f"# {REPORT_TITLE}\n\n"
    final_report += f"> 📅 **生成日期**：{today_str}\n"
    final_report += f"> 💡 **频道**：{TARGET_TOPIC}\n\n---\n\n"
    
    final_report += process_news_pipeline(raw_news, limit=4)
    
    if len(final_report) > 18000:
        final_report = final_report[:18000] + "\n\n> ⚠️ *内容过长已截断*"

    try:
        print("📡 正在推送到微信...")
        response = requests.post("https://www.pushplus.plus/send", json={
            "token": PUSHPLUS_TOKEN,
            "title": f"【{TARGET_TOPIC}】{today_str} 情报简报",
            "content": final_report,
            "template": "markdown"
        }, timeout=15)
        
        print(f"📡 PushPlus 真实回执: {response.text}")
        if response.status_code == 200 and '"code":200' in response.text:
            print("✅ 微信推送成功！")
            
    except Exception as e:
        print(f"❌ 推送失败: {e}")
