from aiogram.fsm.state import State, StatesGroup

class DepositStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_proof = State()

class SearchStates(StatesGroup):
    waiting_for_query = State()

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
