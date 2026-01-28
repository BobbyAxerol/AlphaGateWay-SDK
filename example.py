import asyncio
import logging
import random
from sdk.client import AlphaGateWaySDK
from sdk.models import PositionSide
from shared.config import settings  # Sử dụng instance đã khởi tạo
from shared.database_module import db  # Sử dụng instance db đã khởi tạo

# Cấu hình Logging để quan sát quá trình chạy test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SystemIntegratorTest")

# Gateway URL lấy từ môi trường hoặc mặc định (Lưu ý: Không dùng URL của Redis)
GATEWAY_URL = "http://gateway_service:8000" 

class ComprehensiveTradingTest:
    def __init__(self):
        # Case 1 & 3: Sử dụng Alpha ID riêng để test tính biệt lập
        self.sdk_single = AlphaGateWaySDK(GATEWAY_URL, "ALPHA_TEST_SINGLE")
        # Case 2: Bulk Order Alpha ID
        self.sdk_bulk = AlphaGateWaySDK(GATEWAY_URL, "ALPHA_TEST_BULK")
        # Case 4 & 5: Advanced Order Alpha ID
        self.sdk_adv = AlphaGateWaySDK(GATEWAY_URL, "ALPHA_TEST_ADVANCED")
        
        self.test_symbols = ["ETHUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT", "SOLUSDT"]
        self.is_running = True

    async def log_result(self, case_name: str, result: any, ok: bool):
        status = "✅ SUCCESS" if ok else "❌ FAILED"
        logger.info(f"[{case_name}] {status} | Result: {result}")

    # --- CASE 1: SINGLE ORDER FLOW (Mỗi 5 phút) ---
    async def run_case_1(self):
        """Test Open/Close Long/Short đơn lẻ lần lượt"""
        logger.info("🎬 Starting Case 1: Single Order Cycle")
        symbols = ["ETHUSDT", "BNBUSDT"]
        
        while self.is_running:
            for sym in symbols:
                # 1. Open Long
                res, ok = await self.sdk_single.open_long(sym, 0.01)
                await self.log_result(f"C1: Open Long {sym}", res, ok)
                await asyncio.sleep(2)

                # 2. Close Long
                res, ok = await self.sdk_single.close_long(sym, 0.01)
                await self.log_result(f"C1: Close Long {sym}", res, ok)
                await asyncio.sleep(2)

                # 3. Open Short
                res, ok = await self.sdk_single.open_short(sym, 0.01)
                await self.log_result(f"C1: Open Short {sym}", res, ok)
                await asyncio.sleep(2)

                # 4. Close Short
                res, ok = await self.sdk_single.close_short(sym, 0.01)
                await self.log_result(f"C1: Close Short {sym}", res, ok)

            logger.info("--- Case 1 nghỉ 5 phút ---")
            await asyncio.sleep(300)

    # --- CASE 2: BULK OPERATIONS (Mỗi 10 phút) ---
    async def run_case_2(self):
        """Test gửi danh sách nhiều lệnh và đóng đồng loạt"""
        logger.info("🎬 Starting Case 2: Bulk Operations")
        
        while self.is_running:
            # 1. Bulk Open
            orders = [{"symbol": sym, "qty": round(random.uniform(0.01, 0.1), 3)} for sym in self.test_symbols]
            logger.info(f"C2: Sending Bulk Open for {self.test_symbols}")
            results = await self.sdk_bulk.bulk_open_long(orders)
            await self.log_result("C2: Bulk Open Results", results, True)

            logger.info("C2: Positions opened. Waiting 10m to close...")
            await asyncio.sleep(600)

            # 2. Bulk Close
            logger.info("C2: Performing Emergency Close All for Bulk Case")
            res = await self.sdk_bulk.emergency_close_all()
            await self.log_result("C2: Emergency Close Results", res, True)
            
            await asyncio.sleep(10)

    # --- CASE 3: REBALANCE & SCALING (Mỗi 5 phút) ---
    async def run_case_3(self):
        """Test tăng/giảm quy mô vị thế 30-50%"""
        logger.info("🎬 Starting Case 3: Rebalance Scaling")
        sym = "ETHUSDT"
        
        while self.is_running:
            # Bước 1: Mở vị thế gốc
            await self.sdk_single.open_long(sym, 0.02)
            logger.info(f"C3: {sym} initial position 0.02")
            await asyncio.sleep(300)

            # Bước 2: Rebalance tăng (target 0.03)
            logger.info(f"C3: Rebalancing (Increase) target 0.03")
            await self.sdk_single.rebalance_portfolio([
                {"symbol": sym, "target_qty": 0.03, "pos_side": PositionSide.LONG}
            ])
            await asyncio.sleep(300)

            # Bước 3: Rebalance giảm (target 0.01)
            logger.info(f"C3: Rebalancing (Decrease) target 0.01")
            await self.sdk_single.rebalance_portfolio([
                {"symbol": sym, "target_qty": 0.01, "pos_side": PositionSide.LONG}
            ])
            await asyncio.sleep(300)
            
            # Đóng vị thế để dọn dẹp
            await self.sdk_single.emergency_close_all()

    # --- CASE 4 & 5: ADVANCED & UPDATE (Mỗi 3 phút) ---
    async def run_case_4_5(self):
        """Test lệnh Limit và Update (Sửa lệnh treo)"""
        logger.info("🎬 Starting Case 4 & 5: Limit & Update")
        sym = "BNBUSDT"
        
        while self.is_running:
            # 1. Gửi lệnh Limit mua giá thấp
            limit_price = 200.0 
            res, ok = await self.sdk_adv.open_long(sym, 0.01, price=limit_price)
            
            if ok and isinstance(res, dict) and res.get("id"):
                orig_id = res["id"]
                logger.info(f"C4: Limit Order Created: {orig_id} at {limit_price}")
                
                await asyncio.sleep(10)

                # 2. Update lệnh (Case 5)
                new_price = 210.0
                new_qty = 0.015
                logger.info(f"C5: Updating Order {orig_id} to Price {new_price}")
                upd_res, upd_ok = await self.sdk_adv.update_order(sym, orig_id, new_qty, new_price)
                await self.log_result("C5: Update Result", upd_res, upd_ok)

                await asyncio.sleep(20)
                
                # 3. Clean up
                await self.sdk_adv.emergency_close_all()
            
            await asyncio.sleep(180)

    async def start_all_tests(self):
        """Quản lý kết nối hạ tầng và chạy các tác vụ song song"""
        try:
            logger.info("🔗 Đang thiết lập kết nối Database Pool...")
            await db.connect() # Khởi tạo pool từ database_module
            
            logger.info("🚀 Tất cả hệ thống sẵn sàng. Bắt đầu Test Suite...")
            await asyncio.gather(
                self.run_case_1(),
                self.run_case_2(),
                self.run_case_3(),
                self.run_case_4_5()
            )
        except Exception as e:
            logger.error(f"❌ Lỗi nghiêm trọng trong quá trình chạy: {e}")
        finally:
            logger.info("🔌 Đang đóng các kết nối an toàn (Graceful Shutdown)...")
            await db.disconnect() # Đảm bảo không leak connection pool

if __name__ == "__main__":
    test_suite = ComprehensiveTradingTest()
    try:
        asyncio.run(test_suite.start_all_tests())
    except KeyboardInterrupt:
        logger.info("⏹️ Đã dừng test bởi người dùng.")