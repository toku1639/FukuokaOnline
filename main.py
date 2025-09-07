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

SPREADSHEET_ID = "1bMmbM4wdsPnJkCja3nQEdDZQE3QoMHiOV7h14mMXNOI"
GDRIVE_FOLDER_ID = "12JaCAz7UEUjo_WO50TavyVT8vLOAHSlF" # Googleドキュメントを保存するフォルダのID

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
    prompt = f"""
    以下のニュース情報を元に、福岡の読者向けのブログ記事を1つ作成してください。

    # ニュース情報
    - タイトル: {title}
    - 概要: {summary}

    # 作成ルール
    - 必ず下記のXMLタグの形式で出力してください。
    - <title>タグには、SEOを意識した、読者がクリックしたくなるような新しいタイトルを入れてください。
    - <content>タグには、H2見出しを3つ使った、ポジティブで分かりやすい記事本文と、最後のまとめを入れてください。

    # 出力形式
    <article>
    <title>ここに新しいタイトル</title>
    <content>
    ここに記事本文
    </content>
    </article>
    """
    try:
        print(f"🤖 Geminiに「{title}」の記事作成を依頼します...")
        response = model.generate_content(prompt)
        raw_text = response.text
        if '<title>' in raw_text and '</title>' in raw_text and '<content>' in raw_text and '</content>' in raw_text:
            title_part = raw_text.split('<title>')[1].split('</title>')[0].strip()
            content_part = raw_text.split('<content>')[1].split('</content>')[0].strip()
            return title_part, content_part
        else:
            print("❌ Gemini APIエラー: AIの応答が予期したXML形式ではありませんでした。")
            print(f"   AIの応答(先頭500文字): {raw_text[:500]}...")
            return None, None
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")
        return None, None

def post_to_wordpress(title, content):
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

def is_doc_empty(docs_service, doc_id):
    try:
        doc = docs_service.documents().get(documentId=doc_id, fields='body(content)').execute()
        # endIndexが2以下（つまり、ほぼ空）であれば空とみなす
        end_index = doc.get('body').get('content')[-1].get('endIndex')
        return end_index <= 2
    except Exception as e:
        print(f"ドキュメントのチェック中にエラー: {e}")
        return False

def write_to_doc(creds, doc_id, title, content):
    try:
        print(f"📄 ドキュメント「{doc_id}」に書き込みます...")
        docs_service = build('docs', 'v1', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)

        # 1. ドキュメントの名前を変更
        drive_service.files().update(fileId=doc_id, body={'name': title}).execute()

        # 2. 新しい内容を挿入
        requests_insert = [
            {
                'insertText': {
                    'location': { 'index': 1 },
                    'text': content
                }
            }
        ]
        docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests_insert}).execute()
        print(f"✅ ドキュメントを更新しました。")
        return True
    except Exception as e:
        print(f"❌ Googleドキュメント書き込みエラー: {e}")
        return False

def update_spreadsheet_row(gc, row_index, wp_url, article_title):
    try:
        print(f"📝 スプレッドシートの{row_index}行目を更新します...")
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1
        worksheet.update_cell(row_index, 2, wp_url)          # B列にWP URL
        worksheet.update_cell(row_index, 3, article_title) # C列に記事タイトル
        print(f"✅ スプレッドシートを更新しました。")
        return True
    except Exception as e:
        print(f"❌ スプレッドシート更新エラー: {e}")
        return False

def main():
    print("🚀 スクリプトを開始します。")
    if not all([WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_PASSWORD, GEMINI_API_KEY, GDRIVE_API_CREDENTIALS_JSON]):
        print("❌ エラー: 必要な設定が不足しています。")
        return
    
    gdrive_creds = get_gdrive_credentials()
    docs_service = build('docs', 'v1', credentials=gdrive_creds)
    gc = gspread.authorize(gdrive_creds)

    try:
        print("📝 スプレッドシートから利用可能なドキュメントリストを読み込みます...")
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.sheet1
        doc_urls = worksheet.col_values(1) # A列のURLをすべて取得
        if not doc_urls:
            print("❌ エラー: スプレッドシートのA列にドキュメントURLがありません。")
            return
    except Exception as e:
        print(f"❌ スプレッドシート読み込みエラー: {e}")
        return

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
        if not (article_title and article_content):
            continue

        # 利用可能な空のドキュメントを探す
        found_empty_doc = False
        for i, url in enumerate(doc_urls):
            if not url.startswith('https://docs.google.com'): continue
            
            row_index = i + 1
            doc_id = url.split('/d/')[1].split('/')[0]

            if is_doc_empty(docs_service, doc_id):
                print(f"   -> 空のドキュメントを発見: {url} ({row_index}行目)")
                # WordPressに投稿
                wp_url = post_to_wordpress(article_title, article_content)
                # ドキュメントに書き込み
                write_success = write_to_doc(gdrive_creds, doc_id, article_title, article_content)

                if write_success:
                    # スプレッドシートを更新
                    update_spreadsheet_row(gc, row_index, wp_url or "", article_title)
                    add_posted_url(entry.link)
                    processed_count += 1
                    found_empty_doc = True
                    break # 次のニュース記事へ
        
        if not found_empty_doc:
            print("⚠️ 利用可能な空のGoogleドキュメントがスプレッドシートに見つかりませんでした。")
            # 空きがない場合は、これ以上ニュースを処理できないのでループを抜ける
            break

    if processed_count == 0 and feed.entries:
        print("✨ 新しく処理するニュースはありませんでした。（すべて処理済みまたは空きドキュメントなし）")
    print("🏁 スクリプトを終了します。")


if __name__ == "__main__":
    main()