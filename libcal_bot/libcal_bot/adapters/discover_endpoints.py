from playwright.sync_api import sync_playwright
import json

SEAT_URL = "https://libcal.rug.nl/seat/49526"

def discover():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def on_request(req):
            if req.url.endswith("/spaces/availability/grid"):
                print("\n=== AVAILABILITY REQUEST ===")
                print(req.method, req.url)
                try:
                    post_data = req.post_data
                    print("POST DATA (raw):", post_data)
                    # Vaak is dit form-encoded of JSON; probeer JSON:
                    try:
                        print("POST DATA (json):", json.dumps(json.loads(post_data), indent=2))
                    except Exception:
                        pass
                except Exception as e:
                    print("Could not read post data:", e)

        def on_response(resp):
            if resp.url.endswith("/spaces/availability/grid"):
                print("\n=== AVAILABILITY RESPONSE ===")
                print(resp.status, resp.url)
                try:
                    text = resp.text()
                    print("RESPONSE (first 2000 chars):")
                    print(text[:2000])
                except Exception as e:
                    print("Could not read response text:", e)

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(SEAT_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        browser.close()

if __name__ == "__main__":
    discover()
