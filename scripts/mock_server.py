import json
from http.server import BaseHTTPRequestHandler, HTTPServer

class MockServerRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read the payload
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        print(f"\n[{self.date_time_string()}] --- Received POST {self.path} ---")
        
        try:
            # Pretty print the JSON payload
            parsed = json.loads(post_data)
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            print(post_data.decode('utf-8'))
            
        # Send a 200 OK response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status": "received"}')

    def log_message(self, format, *args):
        # Suppress the default HTTP logging to keep console clean
        pass

if __name__ == '__main__':
    port = 8080
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, MockServerRequestHandler)
    print(f"Mock server listening on http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    print("\nMock server stopped.")
