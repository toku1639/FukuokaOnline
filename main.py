import os
import requests
import tweepy
import google.generativeai as genai
import gspread
import json
from base64 import b64encode
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- 設定項目 ---
WORDPRESS_URL = "http://www.fukuoka-online.jp"
WORDPRESS_USER = "dgtrends_fukuoka"
WORDPRESS_PASSWORD = os.environ.get("WP_PASSWORD")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN")
GDRIVE_API_CREDENTIALS_JSON = os.environ.get("GDRIVE_API_CREDENTIALS")

SPREADSHEET_ID = "1wncPu2zohdvEgbTTEUBJAOPLKYTxZ14-nShy3y7ZYHE"
TREND_LOCATION_WOEID = 1110809
MAX_TRENDS_TO_PROCESS = 5

# --- プログラム本体 ---

POSTED_TRENDS_FILE = "posted_trends.txt"

def get_gdrive_credentials():
    """環境変数から認証情報を読み込む"""
    creds_dict = json.loads(GDRIVE_API_CREDENTIALS_JSON)
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    return Credentials.from_service_account_info(creds_dict, scopes=scopes)

def get_posted_trends():
    if not os.path.exists(POSTED_TRENDS_FILE):
        return set()
    with open(POSTED_TRENDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def add_posted_trend(trend_name):
    with open(POSTED_TRENDS_FILE, "a", encoding="utf-8") as f:
        f.write(trend_name + "\n")

def create_google_doc(creds, title, content):
    """Googleドキュメントを作成し、URLを返す"""
    try:
        print("📄 Googleドキュメントの作成を開始します...")
        service = build('docs', 'v1', credentials=creds)
        doc = service.documents().create(body={'title': title}).execute()
        doc_id = doc.get('documentId')
        
        requests = [
            {
                'insertText': {
                    'location': {
                        'index': 1,
                    },
                    'text': content
                }
            }
        ]
        service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
        
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"✅ Googleドキュメントを作成しました: {doc_url}")
        return doc_url
    except Exception as e:
        print(f"❌ Googleドキュメント作成エラー: {e}")
        return None

def update_spreadsheet(creds, wp_url, doc_url):
    """スプレッドシートのB列とC列にURLを追記する"""
    try:
        print("📝 スプレッドシートの更新を開始します...")
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1
        col_b_values = worksheet.col_values(2)
        next_row = len(col_b_values) + 1
        worksheet.update_cell(next_row, 2, wp_url)
        worksheet.update_cell(next_row, 3, doc_url)
        print(f"✅ スプレッドシートのB{next_row}, C{next_row}セルにURLを書き込みました。")
        return True
    except Exception as e:
        print(f"❌ スプレッドシート更新エラー: {e}")
        return False

def post_to_wordpress(title, content):
    # ... (以前のコードとほぼ同じ、エラー時のレスポンス表示を修正)
    api_url = f"{WORDPRESS_URL}/wp-json/wp/v2/posts"
    credentials = f"{WORDPRESS_USER}:{WORDPRESS_PASSWORD}"
    token = b64encode(credentials.encode('utf-8')).decode('ascii')
    headers = {'Authorization': f'Basic {token}'}
    post_data = {'title': title, 'content': content, 'status': 'draft'}
    try:
        response = requests.post(api_url, headers=headers, json=post_data)
        response.raise_for_status()
        post_url = response.json().get("link")
        print(f"✅ 記事「{title}」をWordPressに下書き投稿しました。")
        return post_url
    except requests.exceptions.RequestException as e:
        print(f"❌ WordPress投稿エラー: {e}")
        # responseが定義されているか確認
        if 'response' in locals() and response:
            print(f"レスポンス内容: {response.text}")
        return None

# get_twitter_trends と create_article_with_gemini は変更なし
def get_twitter_trends():
    if not TWITTER_BEARER_TOKEN: return []
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
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    prompt = f"""...""" # プロンプト内容は変更なし
    try:
        print(f"🤖 Geminiに「{trend_keyword}」の記事作成を依頼します...")
        response = model.generate_content(prompt)
        title_part = response.text.split('[タイトル]')[1].split('[本文]')[0].strip()
        content_part = response.text.split('[本文]')[1].strip()
        return title_part, content_part
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return None, None

def main():
    print("🚀 スクリプトを開始します。")
    if not all([WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_PASSWORD, GEMINI_API_KEY, TWITTER_BEARER_TOKEN, GDRIVE_API_CREDENTIALS_JSON]):
        print("❌ エラー: 必要な設定が不足しています。")
        return

    gdrive_creds = get_gdrive_credentials()
    trends = get_twitter_trends()
    posted_trends = get_posted_trends()
    processed_count = 0

    for trend_name in trends:
        if processed_count >= MAX_TRENDS_TO_PROCESS: break
        if trend_name in posted_trends: continue

        print(f"\n🔥 新しいトレンドを発見: {trend_name}")
        article_title, article_content = create_article_with_gemini(trend_name)

        if article_title and article_content:
            wp_url = post_to_wordpress(article_title, article_content)
            if wp_url:
                doc_url = create_google_doc(gdrive_creds, article_title, article_content)
                if doc_url:
                    update_spreadsheet(gdrive_creds, wp_url, doc_url)
                add_posted_trend(trend_name)
        
        processed_count += 1

    if processed_count == 0:
        print("✨ 新しく処理するトレンドはありませんでした。")

    print("🏁 スクリプトを終了します。")

if __name__ == "__main__":
    main()
