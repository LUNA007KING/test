import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config.settings import BOT_API_TOKEN  # 假设您已将BOT_API_TOKEN移动到了settings.py中

logger = logging.getLogger(__name__)


# 命令处理器
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'group':
        user_status = await context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                        user_id=update.effective_user.id)
        if user_status.status not in ('administrator', 'creator'):
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Sorry, only group admins can query this bot.")
            return
    welcome_msg = """
    Hello👋 <b>Welcome to Namada Validator Bot</b>.

    <b>Commands:</b>
    - <code>/status [address]</code>: Check a validator's current status.
    
    - <code>/monitor [address]</code>: Start monitoring a validator. Notifies on status change. Max 5.
    
    - <code>/view </code>: View status of monitored validators.
    
    - <code>/stop [address|all]</code>: Stop monitoring a validator. Use 'all' to stop all.

    Replace [address] with the validator's address. Use without brackets.
        """
    await update.message.reply_text(welcome_msg, parse_mode='HTML')


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 检查是否提供了地址
    if not context.args:
        await update.message.reply_text("Please provide a validator address.")
        return

    # 获取提供的地址
    validator_address = context.args[0]

    # 假设 fetch_validator_status 是一个已经实现的函数
    # 它从数据库中查询给定地址的validator状态
    validator_status = await fetch_validator_status(validator_address)

    if validator_status is None:
        await update.message.reply_text("This address may not be a validator, or please try again later.")
    else:
        # 格式化validator状态信息为字符串
        status_message = format_validator_status(validator_status)
        await update.message.reply_text(status_message, parse_mode='HTML')


async def monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 从命令中提取验证器地址
    try:
        validator_address = context.args[0]  # 获取用户提供的地址
    except IndexError:
        # 如果用户没有提供地址
        await update.message.reply_text("Please provide a validator address.")
        return

    # 检查地址是否存在于数据库的验证器表中
    if not await fetch_validator_status(validator_address):
        await update.message.reply_text("This address may not be a validator or please try again later.")
        return

    # 检查用户是否已经监控超过5个验证器
    user_id = update.effective_user.id
    if await count_user_monitors(user_id) >= 5:
        await update.message.reply_text(
            "You have reached the monitoring limit of 5 validators. Please remove one before adding another.")
        return

    # 添加监控
    if await add_monitor_for_user(user_id, validator_address):
        await update.message.reply_text(f"Monitoring for validator {validator_address} has been successfully set up.")
    else:
        await update.message.reply_text("There was an error setting up monitoring. Please try again.")


async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id  # 获取用户的Telegram ID

    # 获取用户监控的所有验证器的状态
    monitored_validators_status = await fetch_monitored_validators_status(user_id)

    if not monitored_validators_status:
        # 如果用户没有监控任何验证器
        await update.message.reply_text("You are not monitoring any validators at the moment.")
    else:
        # 如果用户监控了验证器，格式化并发送状态信息
        status_messages = []
        for validator_status in monitored_validators_status:
            # 假设 validator_status 是包含验证器地址和状态的字典
            # 例如：{'address': '0x...', 'status': 'Active'}
            status_message = f"Address: <code>{validator_status['address']}</code> - Status: <b>{validator_status['status']}</b>"
            status_messages.append(status_message)
        await update.message.reply_text("\n".join(status_messages), parse_mode='HTML')


# 错误处理器
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} caused error {context.error}")


def setup_handlers(application):
    """设置Telegram机器人的命令处理和错误处理器。"""
    application.add_handler(CommandHandler("start", start_command))
    application.add_error_handler(error_handler)


def main():
    """初始化并启动Telegram机器人应用。"""
    application = Application.builder().token(BOT_API_TOKEN).build()
    setup_handlers(application)
    application.run_polling()
