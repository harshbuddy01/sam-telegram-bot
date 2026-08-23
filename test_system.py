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
    create_manual_order,
    fulfill_manual_order,
    cancel_and_refund_order,
    get_pending_manual_orders,
    get_available_stock_count,
    get_unsold_stock_by_variant,
    delete_unsold_stock_by_variant,
    add_stock_bulk,
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
    print("\n[1/7] Initializing DB and running seed_initial_data()...")
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
    print("  -> DB Initialized and Seeded successfully!")

    # 2. Check Categories & Products
    print("\n[2/7] Verifying Catalog Hierarchy & Dual Fulfillment Types...")
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

        # Check Netflix (AUTOMATIC) & YouTube (MANUAL)
        netflix = [p for p in prods if "Netflix" in p.title][0]
        n_vars = await get_variants_by_product(session, netflix.id)
        print(f"  -> Found {len(n_vars)} plans under '{netflix.title}':")
        for v in n_vars:
            stock = await get_available_stock_count(session, v.id)
            print(f"     • {v.name} | Price: ₹{v.price} | Mode: {v.fulfillment_type} | Stock: {stock}")
            assert v.fulfillment_type == "AUTOMATIC", "Netflix plans should be AUTOMATIC"

        youtube = [p for p in prods if "YouTube" in p.title][0]
        y_vars = await get_variants_by_product(session, youtube.id)
        for v in y_vars:
            print(f"     • {v.name} | Price: ₹{v.price} | Mode: {v.fulfillment_type} | Dispatch: {v.manual_dispatch_time}")
            assert v.fulfillment_type == "MANUAL", "YouTube invite plans should be MANUAL"

    # 3. Test Automatic Stock Order & Inventory Management
    print("\n[3/7] Testing Automatic Stock Fulfillment & Inventory CRUD...")
    async with AsyncSessionLocal() as session:
        test_uid = 999888777
        user, is_new = await get_or_create_user(
            session=session,
            telegram_id=test_uid,
            username="test_buyer",
            full_name="Test Buyer"
        )
        await update_user_balance(session, test_uid, 1000.0)
        
        v_auto = n_vars[0]
        # Add 2 stock items
        added = await add_stock_bulk(session, v_auto.id, [
            "netflix_acc1@mail.com:pass123 | PIN: 1111",
            "netflix_acc2@mail.com:pass456 | PIN: 2222"
        ])
        print(f"  -> Added {added} accounts to live stock for '{v_auto.name}'")
        
        unsold = await get_unsold_stock_by_variant(session, v_auto.id)
        assert len(unsold) >= 2, "Unsold stock should have at least 2 items"
        print(f"  -> Unsold stock inspection verified: {len(unsold)} items in inventory")

        # Purchase 1 item
        stock_before = await get_available_stock_count(session, v_auto.id)
        order, err = await fulfill_order(session, test_uid, v_auto.id, v_auto.price)
        assert err is None, f"Order failed: {err}"
        assert order.status == "COMPLETED", "Automatic order should be COMPLETED"
        print(f"  -> Auto-delivered Order #{order.id} with content: {order.delivered_content}")
        
        stock_after = await get_available_stock_count(session, v_auto.id)
        assert stock_after == stock_before - 1, "Stock was not decremented!"

    # 4. Test Manual Order Creation, Admin Dispatch & Delivery
    print("\n[4/7] Testing Manual 1-2h Dispatch Order Lifecycle...")
    async with AsyncSessionLocal() as session:
        v_manual = y_vars[0]
        cust_email = "vip_buyer@gmail.com"
        
        # User places manual order
        man_order, err = await create_manual_order(
            session=session,
            user_id=test_uid,
            variant_id=v_manual.id,
            amount=v_manual.price,
            customer_input=cust_email
        )
        assert err is None, f"Manual order failed: {err}"
        assert man_order.status == "PENDING_DISPATCH", "Order status should be PENDING_DISPATCH"
        assert man_order.customer_input == cust_email, "Customer input was not saved"
        print(f"  -> Created Manual Order #{man_order.id} in PENDING_DISPATCH state")

        # Admin lists pending orders
        pending_list = await get_pending_manual_orders(session)
        assert any(o.id == man_order.id for o in pending_list), "Order should be in pending list"
        print(f"  -> Found {len(pending_list)} pending manual order(s) in Admin hub")

        # Admin fulfills order
        invite_link = "https://families.google.com/join/invite_token_xyz"
        fulfilled_order, user = await fulfill_manual_order(session, man_order.id, invite_link)
        assert fulfilled_order.status == "COMPLETED", "Order status should now be COMPLETED"
        assert fulfilled_order.delivered_content == invite_link, "Invite link was not saved"
        print(f"  -> Admin fulfilled Order #{fulfilled_order.id} with link: {fulfilled_order.delivered_content}")

    # 5. Test Manual Order Cancel & Refund
    print("\n[5/7] Testing Manual Order Cancel & Refund Workflow...")
    async with AsyncSessionLocal() as session:
        v_manual = y_vars[0]
        man_order2, _ = await create_manual_order(
            session=session,
            user_id=test_uid,
            variant_id=v_manual.id,
            amount=v_manual.price,
            customer_input="bad_email@xyz.com"
        )
        balance_before_refund = (await get_or_create_user(session, test_uid, "test_buyer", "Test Buyer"))[0].balance
        
        # Cancel & refund
        cancelled_order, refunded_user = await cancel_and_refund_order(session, man_order2.id)
        assert cancelled_order.status == "CANCELLED", "Order should be CANCELLED"
        assert refunded_user.balance == balance_before_refund + v_manual.price, "Balance was not refunded!"
        print(f"  -> Order #{cancelled_order.id} Cancelled & ₹{v_manual.price} successfully refunded to user!")

    # 6. Test QR Code Generator
    print("\n[6/7] Testing UPI QR Code Generator...")
    qr_buf = generate_upi_qr(amount=129.0, note="Test_Order")
    qr_bytes = qr_buf.getvalue()
    print(f"  -> Generated QR Code image buffer: {len(qr_bytes)} bytes")
    assert len(qr_bytes) > 500, "QR code image buffer is too small!"

    # 7. Test Admin Analytics
    print("\n[7/7] Testing Admin Analytics...")
    async with AsyncSessionLocal() as session:
        total_orders, revenue = await get_total_orders_and_revenue(session)
        print(f"  -> Total Orders: {total_orders} | Total Sales: ₹{revenue}")
        assert total_orders >= 2, "Total orders should be at least 2"

    print("\n==============================================")
    print("   ALL TESTS & VERIFICATIONS PASSED (7/7)!   ")
    print("==============================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
