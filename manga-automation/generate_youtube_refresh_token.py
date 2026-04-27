#!/usr/bin/env python3
"""
Generate a new YouTube refresh token using OAuth 2.0 flow.
This script forces consent to get a new refresh token after updating client credentials.
"""

import os
import webbrowser
import json
from urllib.parse import urlencode
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import threading
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if 'code' in self.path:
            # Extract authorization code from callback
            query = self.path.split('?')[1] if '?' in self.path else ''
            params = dict(urllib.parse.parse_qsl(query))
            
            if 'code' in params:
                self.server.auth_code = params['code']
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<html><body><h1>Authorization successful!</h1><p>You can close this window.</p></body></html>')
                return
        
        self.send_response(400)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<html><body><h1>Authorization failed</h1></body></html>')

def generate_refresh_token():
    # Your credentials - Load from environment variables
    CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
    REDIRECT_URI = "http://localhost:8888/callback"
    SCOPE = "https://www.googleapis.com/auth/youtube.upload"
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ Error: YOUTUBE_CLIENT_ID or YOUTUBE_CLIENT_SECRET not found in .env file!")
        print("Please ensure your .env file is configured correctly.")
        return None
    
    print("🔑 YouTube Refresh Token Generator")
    print("=" * 50)
    print(f"Client ID: {CLIENT_ID}")
    print(f"Redirect URI: {REDIRECT_URI}")
    print(f"Scope: {SCOPE}")
    print()
    
    # Step 1: Build authorization URL with forced consent
    auth_params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE,
        'response_type': 'code',
        'access_type': 'offline',  # Required for refresh token
        'prompt': 'consent',       # Forces consent screen
        'state': 'random_state_string'
    }
    
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(auth_params)}"
    
    print("🌐 Step 1: Authorization URL")
    print(auth_url)
    print()
    
    # Step 2: Start local server to handle callback
    server = HTTPServer(('localhost', 8888), CallbackHandler)
    server.auth_code = None
    
    print("🚀 Step 2: Starting local server on port 8888...")
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    # Step 3: Open browser for authorization
    print("🌍 Opening browser for authorization...")
    print("If browser doesn't open, manually visit the URL above")
    webbrowser.open(auth_url)
    
    # Step 4: Wait for authorization code
    print("⏳ Waiting for authorization...")
    timeout = 120  # 2 minutes
    start_time = time.time()
    
    while not server.auth_code and (time.time() - start_time) < timeout:
        time.sleep(1)
    
    server.shutdown()
    server_thread.join()
    
    if not server.auth_code:
        print("❌ Authorization timed out!")
        return None
    
    print(f"✅ Received authorization code: {server.auth_code[:20]}...")
    
    # Step 5: Exchange authorization code for tokens
    token_data = {
        'code': server.auth_code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    print("🔄 Step 3: Exchanging authorization code for tokens...")
    
    try:
        token_request = urllib.request.Request(
            'https://oauth2.googleapis.com/token',
            data=urlencode(token_data).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        with urllib.request.urlopen(token_request) as response:
            token_response = json.loads(response.read().decode())
            
        if 'refresh_token' in token_response:
            refresh_token = token_response['refresh_token']
            access_token = token_response.get('access_token')
            
            print("🎉 SUCCESS! New tokens generated:")
            print("=" * 50)
            print(f"🔑 Refresh Token: {refresh_token}")
            print(f"🎫 Access Token: {access_token[:50]}...")
            print()
            print("📝 Add this to your .env file:")
            print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")
            print()
            print("💡 Your refresh token will work with the updated client credentials!")
            
            return refresh_token
        else:
            print("❌ No refresh token received!")
            print("Response:", token_response)
            return None
            
    except Exception as e:
        print(f"❌ Error exchanging code for tokens: {e}")
        return None

if __name__ == "__main__":
    refresh_token = generate_refresh_token()
    if refresh_token:
        print("\n✅ Refresh token generation completed successfully!")
    else:
        print("\n❌ Refresh token generation failed!")
