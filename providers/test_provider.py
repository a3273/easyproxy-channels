import sys
sys.path.insert(0, '.')

print("=== TEST DADDYLIVE ===")
try:
    from providers.daddy import get_stream
    s = get_stream('Sky Sport Uno')
    print("✓ SUCCESS")
    print("URL:", s['url'][:80] + "...")
    print("Referer:", s['headers']['Referer'])
except Exception as e:
    print("✗ FAILED:", type(e).__name__, str(e))

print("\n=== TEST CDNLIVETV ===")
try:
    from providers.cdn import get_stream
    s = get_stream('Sky Sport Uno')
    print("✓ SUCCESS")
    print("URL:", s['url'][:80] + "...")
    print("Referer:", s['headers']['Referer'])
except Exception as e:
    print("✗ FAILED:", type(e).__name__, str(e))
