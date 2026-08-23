import asyncio
import os
from database.database import init_db, AsyncSessionLocal, engine
from database.crud import (
    seed_initial_data,
    get_active_categories,
    get_products_by_category,
    get_variants_by_product,
    get_variant,
    get_or_create_user,
    fulfill_order,
    get_available_stock_count,
    update_user_balance,
    get_total_orders_and_revenue
)
from utils.qr_generator import generate_upi_qr
from utils.emojis import format_emoji, Emojis

async def run_tests():
    print("==============================================")
    print("   RUNNING TELEGRAM STORE BOT VERIFICATION    ")
    print("==============================================")

    # 1. Initialize DB and Seed Data
    print("\n[1/6] Initializing DB and running seed_initial_data()...")
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
    print("  -> DB Initialized and Seeded successfully!")

    # 2. Check Categories & Products
    print("\n[2/6] Verifying Catalog Hierarchy (Category -> Product -> Variant)...")
    async with AsyncSessionLocal() as session:
        cats = await get_active_categories(session)
        print(f"  -> Found {len(cats)} categories:")
        for c in cats:
            print(f"     • {c.emoji} {c.name} (ID: {c.id})")
        
        # Test Streaming category products
        streaming_cat = cats[0]
        prods = await get_products_by_category(session, streaming_cat.id)
        print(f"  -> Found {len(prods)} products under '{streaming_cat.name}':")
        for p in prods:
            print(f"     • {p.emoji} {p.title}")

        # Check Netflix variants
        netflix = [p for p in prods if "Netflix" in p.title][0]
        variants = await get_variants_by_product(session, netflix.id)
        print(f"  -> Found {len(variants)} plans under '{netflix.title}':")
        for v in variants:
            stock = await get_available_stock_count(session, v.id)
            print(f"     • {v.name} | Price: ₹{v.price} | Stock: {stock}")

    # 3. Test Detailed Description Screen data
    print("\n[3/6] Verifying Detailed Product Description Card...")
    async with AsyncSessionLocal() as session:
        v1 = variants[0]
        print(f"  -> Plan: {v1.name}")
        print(f"  -> Detailed Description Preview:\n{v1.detailed_description}")
        assert v1.detailed_description is not None, "Detailed description should not be None!"

    # 4. Test User, Wallet Deposit & Order Fulfillment
    print("\n[4/6] Testing User creation, Wallet Deposit & Order Auto-Delivery...")
    async with AsyncSessionLocal() as session:
        test_uid = 999888777
        user, is_new = await get_or_create_user(
            session=session,
            telegram_id=test_uid,
            username="test_buyer",
            full_name="Test Buyer"
        )
        print(f"  -> Created test user: {user.full_name} (Balance: ₹{user.balance})")

        # Deposit ₹500
        await update_user_balance(session, test_uid, 500.0)
        user = await get_or_create_user(session, test_uid, "test_buyer", "Test Buyer")
        print(f"  -> Credited ₹500. New balance: ₹{user[0].balance}")

        # Add a fresh test stock item
        from database.crud import add_stock_bulk
        await add_stock_bulk(session, v1.id, ["test_account@mail.com:secretPass123 | Pin: 0000"])

        # Buy v1 (₹99)
        stock_before = await get_available_stock_count(session, v1.id)
        print(f"  -> Stock before purchase: {stock_before}")
        order, err = await fulfill_order(session, test_uid, v1.id, v1.price)
        assert err is None, f"Order fulfillment failed with: {err}"
        print(f"  -> Order #{order.id} Placed!")
        print(f"  -> Delivered Content: {order.delivered_content}")
        
        stock_after = await get_available_stock_count(session, v1.id)
        print(f"  -> Stock after purchase: {stock_after} (Expected: {stock_before - 1})")
        assert stock_after == stock_before - 1, "Stock was not decremented correctly!"

    # 5. Test QR Code Generator
    print("\n[5/6] Testing UPI QR Code Generator...")
    qr_buf = generate_upi_qr(amount=129.0, note="Test_Order")
    qr_bytes = qr_buf.getvalue()
    print(f"  -> Generated QR Code image buffer: {len(qr_bytes)} bytes")
    assert len(qr_bytes) > 500, "QR code image buffer is too small!"

    # 6. Test Admin Metrics
    print("\n[6/6] Testing Admin Metrics...")
    async with AsyncSessionLocal() as session:
        total_orders, revenue = await get_total_orders_and_revenue(session)
        print(f"  -> Total Orders: {total_orders} | Total Sales: ₹{revenue}")
        assert total_orders >= 1, "Total orders should be at least 1"
        assert revenue >= 99.0, "Total revenue should be at least 99.0"

    print("\n==============================================")
    print("   ALL TESTS & VERIFICATIONS PASSED (6/6)!   ")
    print("==============================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
