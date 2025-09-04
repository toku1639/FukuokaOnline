import os
import requests
import feedparser
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
GDRIVE_API_CREDENTIALS_JSON = os.environ.get("GDRIVE_API_CREDENTIALS")

SPREADSHEET_ID = "1wncPu2zohdvEgbTTEUBJAOPLKYTxZ14-nShy3y7ZYHE"
GDRIVE_FOLDER_ID = "13pn0SHHydeIxjgewummgD4ulMiyWKsuv" # Googleドキュメントを保存するフォルダのID

RSS_FEED_URL = "https://news.google.com/rss/search?q=福岡&hl=ja&gl=JP&ceid=JP:ja"
MAX_ARTICLES_TO_PROCESS = 5

# --- プログラム本体 ---

POSTED_URLS_FILE = "posted_urls.txt"

def get_gdrive_credentials():
    creds_dict = json.loads(GDRIVE_API_CREDENTIALS_JSON)
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    return Credentials.from_service_account_info(creds_dict, scopes=scopes)

def get_posted_urls():
    if not os.path.exists(POSTED_URLS_FILE):
        return set()
    with open(POSTED_URLS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def add_posted_url(url):
    with open(POSTED_URLS_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def create_article_with_gemini(title, summary):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""...""" # (プロンプト部分は変更なし)
    try:
        print(f"🤖 Geminiに「{title}」の記事作成を依頼します...")
        response = model.generate_content(prompt)
        title_part = response.text.split('[タイトル]')[1].split('[本文]')[0].strip()
        content_part = response.text.split('[本文]')[1].strip()
        return title_part, content_part
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return None, None

def post_to_wordpress(title, content):
    # ... (変更なし)
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
        if 'response' in locals() and response:
            print(f"レスポンス内容: {response.text}")
        return None

def create_google_doc(creds, title, content):
    try:
        print("📄 Googleドキュメントの作成を開始します...")
        # Docs APIでドキュメントを作成
        docs_service = build('docs', 'v1', credentials=creds)
        doc = docs_service.documents().create(body={'title': title}).execute()
        doc_id = doc.get('documentId')
        
        # Docs APIで内容を書き込み
        requests_body = [{'insertText': {'location': {'index': 1}, 'text': content}}]
        docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests_body}).execute()

        # Drive APIで指定フォルダに移動
        drive_service = build('drive', 'v3', credentials=creds)
        file = drive_service.files().get(fileId=doc_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        drive_service.files().update(
            fileId=doc_id,
            addParents=GDRIVE_FOLDER_ID,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"✅ Googleドキュメントを作成し、指定フォルダに移動しました: {doc_url}")
        return doc_url
    except Exception as e:
        print(f"❌ Googleドキュメント作成エラー: {e}")
        return None

def update_spreadsheet(creds, wp_url, doc_url):
    # ... (変更なし)
    try:
        print("📝 スプレッドシートの更新を開始します...")
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1
        col_b_values = worksheet.col_values(2)
        next_row = len(col_b_values) + 1
        if wp_url: worksheet.update_cell(next_row, 2, wp_url)
        if doc_url: worksheet.update_cell(next_row, 3, doc_url)
        print(f"✅ スプレッドシートのB{next_row}, C{next_row}セルにURLを書き込みました。")
        return True
    except Exception as e:
        print(f"❌ スプレッドシート更新エラー: {e}")
        return False

def main():
    # ... (変更なし)
    print("🚀 スクリプトを開始します。")
    if not all([WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_PASSWORD, GEMINI_API_KEY, GDRIVE_API_CREDENTIALS_JSON]):
        print("❌ エラー: 必要な設定が不足しています。")
        return

    gdrive_creds = get_gdrive_credentials()
    feed = feedparser.parse(RSS_FEED_URL)
    posted_urls = get_posted_urls()
    processed_count = 0

    if not feed.entries:
        print("📰 新しいニュースはありませんでした。")

    for entry in reversed(feed.entries):
        if processed_count >= MAX_ARTICLES_TO_PROCESS: 
            print(f"🔍 処理上限（{MAX_ARTICLES_TO_PROCESS}件）に達したため、終了します。")
            break
        if entry.link in posted_urls: continue

        print(f"\n🔥 新しいニュースを発見: {entry.title}")
        article_title, article_content = create_article_with_gemini(entry.title, entry.summary)

        if article_title and article_content:
            wp_url = post_to_wordpress(article_title, article_content)
            doc_url = create_google_doc(gdrive_creds, article_title, article_content)

            if wp_url or doc_url:
                update_spreadsheet(gdrive_creds, wp_url or "", doc_url or "")
            
            if doc_url:
                add_posted_url(entry.link)
        
        processed_count += 1

    if processed_count == 0 and feed.entries:
        print("✨ 新しく処理するニュースはありませんでした。（すべて処理済み）")

    print("🏁 スクリプトを終了します。")

if __name__ == "__main__":
    main()