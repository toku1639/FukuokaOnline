import os
import requests
import tweepy
import google.generativeai as genai
import gspread
import json
from base64 import b64encode

# --- 設定項目 ---

### ▼▼▼ 修正が必要 ① ▼▼▼ ###
# あなたのWordPressサイトの情報を入力
WORDPRESS_URL = "http://www.fukuoka-online.jp"
WORDPRESS_USER = "dgtrends_fukuoka"
# 以下はGitHub Secretsから読み込む
WORDPRESS_PASSWORD = os.environ.get("WP_PASSWORD")

### ▼▼▼ 修正が必要 ② ▼▼▼ ###
# 各APIキーを環境変数から読み込む
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN")
GDRIVE_API_CREDENTIALS_JSON = os.environ.get("GDRIVE_API_CREDENTIALS")

### ▼▼▼ 修正が必要 ③ ▼▼▼ ###
# 書き込みたいGoogleスプレッドシートのID
# URL (https://docs.google.com/spreadsheets/d/ココがID/edit#gid=0) から取得
SPREADSHEET_ID = "1wncPu2zohdvEgbTTEUBJAOPLKYTxZ14-nShy3y7ZYHE"

### ▼▼▼ 修正が必要 ④ (お好みで) ▼▼▼ ###
# トレンドを取得する場所のWOEID (Worldwide Yahoo! Weather-ID)
TREND_LOCATION_WOEID = 1110809 # 日本のトレンド

# 一度に処理するトレンドの最大数
MAX_TRENDS_TO_PROCESS = 5

# --- プログラム本体 (ここからは基本的に修正不要) ---

# 投稿済みトレンドを記録するファイル
POSTED_TRENDS_FILE = "posted_trends.txt"

def get_posted_trends():
    """投稿済みのトレンドをファイルから読み込む"""
    if not os.path.exists(POSTED_TRENDS_FILE):
        return set()
    with open(POSTED_TRENDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def add_posted_trend(trend_name):
    """投稿済みのトレンドをファイルに追記する"""
    with open(POSTED_TRENDS_FILE, "a", encoding="utf-8") as f:
        f.write(trend_name + "\n")

def get_twitter_trends():
    """X (Twitter) API v1.1 を使ってトレンドを取得する"""
    # ... (変更なし)

def create_article_with_gemini(trend_keyword):
    """Gemini APIを使ってトレンドに関する記事を生成する"""
    # ... (変更なし)

def post_to_wordpress(title, content): 
    """WordPressに記事を投稿し、成功したら記事URLを返す"""
    api_url = f"{WORDPRESS_URL}/wp-json/wp/v2/posts"
    credentials = f"{WORDPRESS_USER}:{WORDPRESS_PASSWORD}"
    token = b64encode(credentials.encode('utf-8')).decode('ascii')
    headers = {'Authorization': f'Basic {token}'}
    post_data = {
        'title': title,
        'content': content,
        'status': 'draft',
    }
    try:
        response = requests.post(api_url, headers=headers, json=post_data)
        response.raise_for_status()
        post_url = response.json().get("link")
        print(f"✅ 記事「{title}」をWordPressに下書き投稿しました。")
        return post_url
    except requests.exceptions.RequestException as e:
        print(f"❌ WordPress投稿エラー: {e}")
        if response:
            print(f"レスポンス内容: {response.text}")
        return None

def update_spreadsheet(post_url):
    """スプレッドシートのB列にURLを追記する"""
    try:
        print("📝 スプレッドシートの更新を開始します...")
        creds_dict = json.loads(GDRIVE_API_CREDENTIALS_JSON)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1
        # B列の最初の空のセルを探す
        col_b_values = worksheet.col_values(2)
        next_row = len(col_b_values) + 1
        worksheet.update_cell(next_row, 2, post_url)
        print(f"✅ スプレッドシートのB{next_row}セルにURLを書き込みました。")
        return True
    except Exception as e:
        print(f"❌ スプレッドシート更新エラー: {e}")
        return False

def main():
    """メインの処理"""
    print("🚀 スクリプトを開始します。")
    
    if not all([WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_PASSWORD, GEMINI_API_KEY, TWITTER_BEARER_TOKEN, GDRIVE_API_CREDENTIALS_JSON]):
        print("❌ エラー: 必要な設定（WordPress情報、各種APIキー）が不足しています。")
        return

    trends = get_twitter_trends()
    posted_trends = get_posted_trends()
    
    new_trends_found = False
    processed_count = 0
    
    for trend_name in trends:
        if processed_count >= MAX_TRENDS_TO_PROCESS:
            print(f"🔍 処理上限（{MAX_TRENDS_TO_PROCESS}件）に達したため、終了します。")
            break

        if trend_name not in posted_trends:
            new_trends_found = True
            print(f"\n🔥 新しいトレンドを発見: {trend_name}")
            
            article_title, article_content = create_article_with_gemini(trend_name)
            
            if article_title and article_content:
                posted_url = post_to_wordpress(article_title, article_content)
                if posted_url:
                    add_posted_trend(trend_name)
                    update_spreadsheet(posted_url) # スプレッドシート更新処理を呼び出し
            
            processed_count += 1
    
    if not new_trends_found:
        print("✨ 新しく処理するトレンドはありませんでした。")

    print("🏁 スクリプトを終了します。")

# get_twitter_trends と create_article_with_gemini の元のコードをここに含める

def get_twitter_trends():
    """X (Twitter) API v1.1 を使ってトレンドを取得する"""
    if not TWITTER_BEARER_TOKEN:
        print("❌ エラー: TWITTER_BEARER_TOKENが設定されていません。")
        return []
    try:
        auth = tweepy.OAuth2BearerHandler(TWITTER_BEARER_TOKEN)
        api_v1 = tweepy.API(auth)
        trends = api_v1.get_place_trends(id=TREND_LOCATION_WOEID)
        trend_names = [trend["name"] for trend in trends[0]["trends"]]
        print(f"📈 Xから日本のトレンドを{len(trend_names)}件取得しました。")
        return trend_names
    except Exception as e:
        print(f"❌ X (Twitter) APIエラー: {e}")
        return []

def create_article_with_gemini(trend_keyword):
    """Gemini APIを使ってトレンドに関する記事を生成する"""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    prompt = f"""
    現在、X(旧Twitter)で「{trend_keyword}」というキーワードがトレンドになっています。
    このトレンドワードをテーマに、SEOを意識した魅力的なブログ記事を作成してください。

    # 記事作成のルール
    - 福岡のローカル情報に関心がある読者をターゲットにしてください。
    - トレンドに関係なさそうに見えても、何とか福岡の話題に結びつけてください。（例：「〇〇（トレンドワード）が話題ですが、福岡にも〇〇という場所があって…」）
    - 読者が「もっと知りたい」「行ってみたい」「面白い」と思えるような、ポジティブで分かりやすい文章で書いてください。
    - 記事のタイトルは、トレンドワードと福岡を結びつけた、具体的でクリックしたくなるようなものにしてください。
    - 記事の構成は、見出し(H2)と本文の組み合わせで３つ作成してください。
    - 最後に簡単なまとめを作成してください。
    - 必ず日本語で回答してください。

    # 出力形式 (この形式を厳守してください)
    [タイトル]ここに生成したタイトル
    [本文]ここに生成した本文(見出しやまとめを含む)
    """
    try:
        print(f"🤖 Geminiに「{trend_keyword}」の記事作成を依頼します...")
        response = model.generate_content(prompt)
        title_part = response.text.split('[タイトル]')[1].split('[本文]')[0].strip()
        content_part = response.text.split('[本文]')[1].strip()
        return title_part, content_part
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return None, None

if __name__ == "__main__":
    main()