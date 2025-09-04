import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 設定項目 ---
GDRIVE_API_CREDENTIALS_JSON = os.environ.get("GDRIVE_API_CREDENTIALS")

# --- テストプログラム本体 ---

def get_gdrive_credentials():
    creds_dict = json.loads(GDRIVE_API_CREDENTIALS_JSON)
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    return Credentials.from_service_account_info(creds_dict, scopes=scopes)

def main():
    print("🚀 テストスクリプトを開始します。")
    if not GDRIVE_API_CREDENTIALS_JSON:
        print("❌ エラー: 必要な設定が不足しています。")
        return

    try:
        print("🔑 認証情報を取得します...")
        creds = get_gdrive_credentials()
        gc = gspread.authorize(creds)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet_name = f"Gemini Test Sheet {timestamp}"

        print(f"📝 新しいスプレッドシート「{sheet_name}」の作成を試みます...")
        spreadsheet = gc.create(sheet_name)
        print(f"✅ テスト成功！ スプレッドシートを作成しました。")
        print(f"   URL: {spreadsheet.url}")

    except Exception as e:
        print(f"❌ テスト失敗！ エラーが発生しました。")
        print(f"   エラー内容: {e}")
    
    print("🏁 テストスクリプトを終了します。")

if __name__ == "__main__":
    main()
