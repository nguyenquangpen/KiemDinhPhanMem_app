import json
import base64
import sqlite3

conn = sqlite3.connect("agent_local_storage.db")
cursor = conn.cursor()

uuid = "613d8483-10a6-43be-876d-6a145b3ee8e4"

# cursor.execute(
#     "SELECT checkpoint_data FROM testcases WHERE uuid = ?",
#     (uuid,)
# )

# row = cursor.fetchone()

# if row:
#     checkpoint_data = json.loads(row[0])
#     state_b64 = checkpoint_data.get("agent_state")
#     state_data = json.loads(base64.b64decode(state_b64).decode("utf-8"))
#     print("Current state_data:", state_data)


# state_data = {
#     "name": "agent1",
#     "status": "running",
#     "count": 5
# }

# step_number = 3

# Encode state_data
with open("test_db.json", "r") as f:
    state_data = json.load(f)
state_data_str = json.dumps(state_data)
step_number = 3

# Update thẳng DB
cursor.execute(
    """
    UPDATE testcases
    SET step_number = ?,
        checkpoint_data = ?
    WHERE uuid = ?
    """,
    (step_number, state_data_str, uuid)
)

conn.commit()
conn.close()


# ----------------------------------------------------------------------------
# import asyncio
# import json
# from urllib.parse import urlparse
# from playwright.async_api import async_playwright

# class SessionTester:
#     def __init__(self):
#         self.context = None
#         self.browser = None

#     async def get_full_session_state(self, page) -> dict:
#         """Hàm logic bạn vừa viết (đã làm sạch để chạy độc lập)"""
#         # 1. Chụp snapshot trạng thái hiện tại
#         state = await self.context.storage_state()
        
#         # 2. Xác định domain hiện tại để lọc
#         current_domain_parts = urlparse(page.url).netloc.split('.')
#         current_domain_str = ".".join(current_domain_parts[-2:]) # vd: onthivstep.vn

#         # 3. Lọc Cookies liên quan đến domain chính
#         filtered_cookies = [
#             c for c in state.get("cookies", [])
#             if current_domain_str in c["domain"]
#         ]
        
#         # 4. Lọc LocalStorage liên quan đến domain chính
#         filtered_origins = [
#             o for o in state.get("origins", [])
#             if current_domain_str in urlparse(o["origin"]).netloc
#         ]

#         return {
#             "cookies": filtered_cookies,
#             "origins": filtered_origins
#         }

#     async def run_test(self):
#         async with async_playwright() as p:
#             # --- GIAI ĐOẠN 1: LOGIN & CAPTURE ---
#             print("=== GIAI ĐOẠN 1: ĐĂNG NHẬP ===")
#             self.browser = await p.chromium.launch(headless=False)
#             self.context = await self.browser.new_context()
#             page = await self.context.new_page()
            
#             await page.goto("https://onthivstep.vn/dang-nhap")
#             print("Vui lòng thực hiện đăng nhập trên trình duyệt...")
#             print("Sau khi đăng nhập thành công, nhấn ENTER tại terminal để CAPTURE state.")
#             input("Đợi đăng nhập xong rồi nhấn Enter...")
            
#             # Gọi hàm test
#             captured_state = await self.get_full_session_state(page)
            
#             print(f"Đã capture xong! Số cookie: {len(captured_state['cookies'])}")
#             await self.browser.close()

#             # --- GIAI ĐOẠN 2: RESTORE & VERIFY ---
#             print("\n=== GIAI ĐOẠN 2: KHÔI PHỤC THỬ NGHIỆM ===")
#             # Mở một trình duyệt mới hoàn toàn
#             self.browser = await p.chromium.launch(headless=False)
            
#             # Nạp state vào lúc khởi tạo context mới
#             # Đây là cách Backend sẽ dùng để restore
#             self.context = await self.browser.new_context(storage_state=captured_state)
            
#             test_page = await self.context.new_page()
            
#             # Truy cập thẳng vào trang Lịch sử (Trang này yêu cầu login mới xem được)
#             print("Đang truy cập thẳng vào trang bảo mật để kiểm tra session...")
#             await test_page.goto("https://onthivstep.vn/lich-su-giao-dich")
            
#             # Kiểm tra xem có thấy nội dung trang lịch sử hay bị đá ra trang login
#             await asyncio.sleep(5) # Đợi 5s để bạn quan sát màn hình
            
#             current_url = test_page.url
#             if "lich-su-giao-dich" in current_url:
#                 print("✅ THÀNH CÔNG: Session đã được khôi phục, bạn đang ở trang nội bộ.")
#             else:
#                 print("❌ THẤT BẠI: Bạn bị điều hướng sang trang khác (có thể là trang login).")
            
#             await self.browser.close()

# if __name__ == "__main__":
#     tester = SessionTester()
#     asyncio.run(tester.run_test())


# import asyncio
# from playwright.async_api import async_playwright

# async def restore_session():
#     async with async_playwright() as p:
#         # Khởi tạo trình duyệt với file state.json đã lưu
#         browser = await p.chromium.launch(headless=False)
        
#         # ĐÂY LÀ ĐOẠN QUAN TRỌNG: Nạp file state vào context ngay từ đầu
#         context = await browser.new_context(storage_state="state.json")
        
#         page = await context.new_page()
        
#         # Đi thẳng vào trang Lịch sử giao dịch
#         await page.goto("https://onthivstep.vn/lich-su-giao-dich")
        
#         # Kiểm tra xem có còn bắt đăng nhập không
#         await asyncio.sleep(10) 
#         await browser.close()

# if __name__ == "__main__":
#     asyncio.run(restore_session())