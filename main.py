import os
import requests
import feedparser
import google.generativeai as genai
from base64 import b64encode

# --- 設定項目 ---

### ▼▼▼ 修正が必要 ① ▼▼▼ ###
# あなたのWordPressサイトの情報を入力
WORDPRESS_URL = "https://あなたのドメイン.com"
WORDPRESS_USER = "あなたのWPユーザー名"
WORDPRESS_PASSWORD = os.environ.get("WP_PASSWORD") # GitHub Secretsから読み込む

### ▼▼▼ 修正が必要 ② ▼▼▼ ###
# Google AI Studioで取得したAPIキーを設定
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # GitHub Secretsから読み込む

### ▼▼▼ 修正が必要 ③ ▼▼▼ ###
# 情報を取得したいGoogle NewsのRSSフィードURL
# 例: 「福岡」の検索結果
RSS_FEED_URL = "https://news.google.com/rss/search?q=福岡&hl=ja&gl=JP&ceid=JP:ja"

# --- プログラム本体 (ここからは基本的に修正不要) ---

# 投稿済みURLを記録するファイル
POSTED_URLS_FILE = "posted_urls.txt"

def get_posted_urls():
    """投稿済みのURLをファイルから読み込む"""
    if not os.path.exists(POSTED_URLS_FILE):
        return set()
    with open(POSTED_URLS_FILE, "r") as f:
        return set(line.strip() for line in f)

def add_posted_url(url):
    """投稿済みのURLをファイルに追記する"""
    with open(POSTED_URLS_FILE, "a") as f:
        f.write(url + "\n")

def create_article_with_gemini(title, summary):
    """Gemini APIを使って記事を生成する"""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')

    ### ▼▼▼ 修正が必要 ④ (お好みで) ▼▼▼ ###
    # AIへの指示内容（プロンプト）。ここで記事のスタイルが決まります。
    prompt = f"""
    以下のニュースを基に、SEOを意識した魅力的なブログ記事を作成してください。

    # 元ニュースのタイトル
    {title}

    # ニュースの概要
    {summary}

    # 記事作成のルール
    - 福岡のローカル情報に関心がある読者をターゲットにしてください。
    - 読者が「もっと知りたい」「行ってみたい」と思えるような、ポジティブで分かりやすい文章で書いてください。
    - 記事のタイトルは、具体的でクリックしたくなるようなものにしてください。
    - 記事の構成は、見出し(H2)と本文の組み合わせで３つ作成してください。
    - 最後に簡単なまとめを作成してください。
    - 必ず日本語で回答してください。

    # 出力形式 (この形式を厳守してください)
    [タイトル]ここに生成したタイトル
    [本文]ここに生成した本文(見出しやまとめを含む)
    """

    try:
        response = model.generate_content(prompt)
        # 出力形式に合わせてタイトルと本文を分割
        title_part = response.text.split('[タイトル]')[1].split('[本文]')[0].strip()
        content_part = response.text.split('[本文]')[1].strip()
        return title_part, content_part
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return None, None


def post_to_wordpress(title, content):
    """WordPressに記事を投稿する"""
    api_url = f"{WORDPRESS_URL}/wp-json/wp/v2/posts"
    
    # Basic認証のための認証情報を作成
    credentials = f"{WORDPRESS_USER}:{WORDPRESS_PASSWORD}"
    token = b64encode(credentials.encode('utf-8')).decode('ascii')
    headers = {'Authorization': f'Basic {token}'}

    post_data = {
        'title': title,
        'content': content,
        'status': 'draft',  # 'publish'にすると即時公開。安全のため'draft'(下書き)を推奨
        # 'categories': [1, 2], # カテゴリーIDを指定
        # 'tags': [3, 4] # タグIDを指定
    }

    try:
        response = requests.post(api_url, headers=headers, json=post_data)
        response.raise_for_status() # エラーがあれば例外を発生させる
        print(f"✅ 記事「{title}」をWordPressに下書き投稿しました。")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ WordPress投稿エラー: {e}")
        print(f"レスポンス内容: {response.text}")
        return False

def main():
    """メインの処理"""
    print("🚀 スクリプトを開始します。")
    feed = feedparser.parse(RSS_FEED_URL)
    posted_urls = get_posted_urls()
    
    new_articles_found = False
    for entry in reversed(feed.entries): # 古いニュースから順に処理
        if entry.link not in posted_urls:
            new_articles_found = True
            print(f"📰 新しいニュースを発見: {entry.title}")
            
            # AIで記事を生成
            article_title, article_content = create_article_with_gemini(entry.title, entry.summary)
            
            # 投稿処理
            if article_title and article_content:
                if post_to_wordpress(article_title, article_content):
                    add_posted_url(entry.link) # 成功したら記録
    
    if not new_articles_found:
        print("新しいニュースはありませんでした。")

    print("🏁 スクリプトを終了します。")

if __name__ == "__main__":
    main()