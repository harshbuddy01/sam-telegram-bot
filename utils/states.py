from aiogram.fsm.state import State, StatesGroup

class DepositStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_proof = State()

class SearchStates(StatesGroup):
    waiting_for_query = State()

class OrderManualStates(StatesGroup):
    waiting_for_input = State()

class AdminManualOrderStates(StatesGroup):
    waiting_for_fulfillment_content = State()

class AdminCategoryStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_emoji = State()
    waiting_for_custom_emoji_id = State()

class AdminProductStates(StatesGroup):
    waiting_for_category_id = State()
    waiting_for_title = State()
    waiting_for_emoji = State()
    waiting_for_desc = State()
    waiting_for_image = State()

class AdminVariantStates(StatesGroup):
    waiting_for_product_id = State()
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_type = State()
    waiting_for_fulfillment_type = State()
    waiting_for_dispatch_time = State()
    waiting_for_input_prompt = State()
    waiting_for_detailed_desc = State()

class AdminStockStates(StatesGroup):
    waiting_for_variant_id = State()
    waiting_for_stock_lines = State()

class AdminBroadcastStates(StatesGroup):
    waiting_for_content = State()
    waiting_for_confirmation = State()

class AdminUserManagementStates(StatesGroup):
    waiting_for_user_query = State()
    waiting_for_amount_adjust = State()

class AdminVariantEditStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_new_price = State()
    waiting_for_new_desc = State()
    waiting_for_new_dispatch_time = State()
    waiting_for_new_input_prompt = State()

class AdminCategoryEditStates(StatesGroup):
    waiting_for_new_name = State()

class AdminProductEditStates(StatesGroup):
    waiting_for_new_title = State()
    waiting_for_new_desc = State()

class AdminSettingsStates(StatesGroup):
    waiting_for_upi_id = State()
    waiting_for_upi_name = State()
    waiting_for_support_user = State()
    waiting_for_razorpay_key_id = State()
    waiting_for_razorpay_key_secret = State()
    waiting_for_cashfree_app_id = State()
    waiting_for_cashfree_secret_key = State()
