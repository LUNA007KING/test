import re
import subprocess
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from urllib.parse import urljoin
from config.settings import DB_CONFIG, BLOCKCHAIN_RPC_URL
from db.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class Result:
    def __init__(self, success, data=None, error=None):
        self.success = success
        self.data = data
        self.error = error


def create_session_with_retry(retries=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504]):
    retry_strategy = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_height(rpc_endpoint=BLOCKCHAIN_RPC_URL):
    session = create_session_with_retry()
    try:
        normalized_endpoint = urljoin(rpc_endpoint, 'status')
        response = session.get(normalized_endpoint)
        response.raise_for_status()
        data = response.json()

        if 'result' in data and 'sync_info' in data['result']:
            sync_info = data['result']['sync_info']
            latest_block_height = int(sync_info.get('latest_block_height', 0))
            catching_up = bool(sync_info.get('catching_up', False))
            return Result(True, data=(latest_block_height, catching_up))
        else:
            error_msg = 'fetch_height error: JSON data does not contain the required structure.'
            logger.error(error_msg)
            return Result(False, error=error_msg)
    except Exception as e:
        logger.error(str(e))
        return Result(False, error=str(e))
    finally:
        session.close()


def fetch_validators(height, rpc_endpoint=BLOCKCHAIN_RPC_URL):
    validators_info = []
    page = 1
    per_page = 100
    session = create_session_with_retry()

    try:
        while True:
            endpoint_path = f'validators?height={height}&page={page}&per_page={per_page}'
            normalized_endpoint = urljoin(rpc_endpoint, endpoint_path)
            response = session.get(normalized_endpoint)
            response.raise_for_status()
            data = response.json()

            if 'result' in data and 'validators' in data['result']:
                validators = data['result']['validators']
                validators_info.extend([(validator['address'], validator['voting_power']) for validator in validators])
                total_validators = int(data['result']['total'])
                if len(validators_info) >= total_validators:
                    break
                page += 1
            else:
                error_msg = 'fetch_validators error: JSON data does not contain the required structure.'
                logger.error(error_msg)
                return Result(False, error=error_msg)
        return Result(True, data=validators_info)
    except Exception as e:
        logger.error(str(e))
        return Result(False, error=str(e))
    finally:
        session.close()


def parse_tm_address(tm_address, node_url='http://127.0.0.1:26657'):
    if len(tm_address) != 40:
        return Result(False, error="Invalid Tendermint address length. Expected length is 40 characters.")

    try:
        command = ["namadac", "find-validator", "--tm-address", tm_address, "--node", node_url]
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = result.stdout
        validator_address_match = re.search(r'Found validator address "(.*?)"', output)
        consensus_key_match = re.search(r'Consensus key: (.*?)\n', output)

        if validator_address_match and consensus_key_match:
            data = {
                "validator_address": validator_address_match.group(1),
                "consensus_key": consensus_key_match.group(1)
            }
            return Result(True, data=data)
        else:
            error_msg = 'parse_tm_address error: Unable to parse validator address or consensus key.'
            logger.error(error_msg)
            return Result(False, error=error_msg)
    except subprocess.CalledProcessError as e:
        error_msg = f"Command execution failed: {e.stdout.decode()} {e.stderr.decode()}"
        logger.error(error_msg)
        return Result(False, error=error_msg)


def fetch_validator_metadata(validator_address, node_url='http://127.0.0.1:26657'):
    try:
        command = ["namadac", "validator-metadata", "--validator", validator_address, "--node", node_url]

        # Executing the command without using shell=True for security reasons
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = result.stdout
        metadata = {
            'email': re.search(r'Email: (.*)', output).group(1),
            # 'description': re.search(r'Description: (.*)', output).group(1),
            'website': re.search(r'Website: (.*)', output).group(1),
            'discord_handle': re.search(r'Discord handle: (.*)', output).group(1),
            'avatar': re.search(r'Avatar: (.*)', output).group(1),
            'commission_rate': re.search(r'commission rate: ([\d.]+)', output).group(1),
            # 'max_change_per_epoch': re.search(r'max change per epoch: ([\d.]+)', output).group(1),
        }
        return Result(True, data=metadata)
    except subprocess.CalledProcessError as e:
        error_msg = f"Command execution failed: {e.stdout.decode()} {e.stderr.decode()}"
        logger.error(error_msg)
        return Result(False, error=error_msg)
    except AttributeError:
        error_msg = 'fetch_validator_metadata error: Failed to parse some or all validator metadata'
        logger.error(error_msg)
        return Result(False, error=error_msg)


def fetch_validator_state(validator_address, node_url='http://127.0.0.1:26657'):
    try:
        command = ["namadac", "validator-state", "--validator", validator_address, "--node", node_url]
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = result.stdout
        if "is in the consensus set" in output:
            state = "active"
        elif "is in the below-threshold set" in output:
            state = "inactive"
        elif "is jailed" in output:
            state = "jailed"
        elif "is either not a validator, or an epoch before the current epoch has been queried" in output:
            state = "none"
        else:
            error_msg = 'fetch_validator_state error: Unable to determine validator state'
            logger.error(error_msg)
            return Result(False, error=error_msg)
        return Result(True, data=state)
    except subprocess.CalledProcessError as e:
        error_msg = f"Command execution failed: {e.stdout.decode()} {e.stderr.decode()}"
        logger.error(error_msg)
        return Result(False, error=error_msg)


def initialize_database():
    db_manager = DatabaseManager(DB_CONFIG)
    db_manager.create_database()

    db_manager.table_name = 'users'
    db_manager.columns = {
        'user_id': 'INT AUTO_INCREMENT PRIMARY KEY',
        'telegram_id': 'VARCHAR(12) NOT NULL',
        'telegram_name': 'VARCHAR(32)'
    }
    db_manager.create_table()

    db_manager.table_name = 'validators'
    db_manager.columns = {
        'validator_id': 'INT AUTO_INCREMENT PRIMARY KEY',
        'validator_address': 'VARCHAR(45)',
        'tendermint_address': 'VARCHAR(40) NOT NULL',
        'consensus_key': 'VARCHAR(66)',
        'voting_power': 'BIGINT',
        'email': 'VARCHAR(255)',
        'website': 'VARCHAR(255)',
        'discord_handle': 'VARCHAR(50)',
        'avatar': 'VARCHAR(255)',
        'commission_rate': 'FLOAT',
        'status': 'VARCHAR(10)'
    }
    db_manager.create_table()

    db_manager.table_name = 'subscriptions'
    db_manager.columns = {
        'id': 'INT AUTO_INCREMENT PRIMARY KEY',
        'user_id': 'INT NOT NULL',
        'validator_id': 'INT NOT NULL',
        'created_at': 'DATETIME DEFAULT CURRENT_TIMESTAMP'
    }
    foreign_keys = [
        'FOREIGN KEY(user_id) REFERENCES users(user_id)',
        'FOREIGN KEY(validator_id) REFERENCES validators(validator_id)'
    ]
    db_manager.create_table(foreign_keys)


def fetch_subscribed_users(db_manager, validator_id):
    db_manager.table_name = 'subscriptions'
    query = "SELECT user_id FROM subscriptions WHERE validator_id = %s"
    params = (validator_id,)

    try:
        subscribed_users = db_manager.execute_query(query, params)
        return [user[0] for user in subscribed_users]  # 提取 user_id 并返回列表
    except Exception as e:
        logger.error(f"Error fetching subscribed users for validator {validator_id}: {e}")
        return []


def update_blockchain_data():
    print("Updating blockchain data...")
    db_manager = DatabaseManager(DB_CONFIG)

    db_manager.database = DB_CONFIG['database']
    db_manager.table_name = 'validators'

    height_response = fetch_height()
    if not height_response.success:
        return

    height, syncing = height_response.data
    if syncing:
        logger.info(f'Blockchain at {BLOCKCHAIN_RPC_URL} is still syncing. Current height: {height}')
        return

    validators_response = fetch_validators(height)
    if not validators_response.success:
        return

    for validator in validators_response.data:
        tendermint_address, voting_power = validator
        try:
            existing_validator = db_manager.execute_query(
                f"SELECT validator_id FROM {db_manager.table_name} WHERE tendermint_address = %s",
                (tendermint_address,),
                commit=False
            )
            if existing_validator:
                db_manager.update_data(
                    {'tendermint_address': tendermint_address},
                    {'voting_power': voting_power}
                )
            else:
                db_manager.insert_data({
                    'tendermint_address': tendermint_address,
                    'voting_power': voting_power,
                })
        except Exception as e:
            logger.error(f"Error updating or inserting validator: {e}")

    update_address(db_manager)
    update_metadata(db_manager)
    update_status(db_manager)


def update_address(db_manager):
    # 从数据库获取所有验证器的Tendermint地址
    query = "SELECT validator_id, tendermint_address FROM validators"
    validators = db_manager.execute_query(query)

    for validator in validators:
        validator_id, tendermint_address = validator
        parse_result = parse_tm_address(tendermint_address)

        if parse_result.success:
            # 准备更新的数据
            update_data = {
                'validator_address': parse_result.data['validator_address'],
                'consensus_key': parse_result.data['consensus_key']
            }
            # 构建条件和更新数据库
            conditions = {'validator_id': validator_id}
            try:
                db_manager.update_data(conditions, update_data)
                logger.info(f"Validator {validator_id} updated successfully.")
            except Exception as e:
                logger.error(f"Failed to update validator {validator_id}: {e}")
        else:
            logger.error(f"Failed to parse address {tendermint_address}: {parse_result.error}")


def update_metadata(db_manager):
    query = "SELECT validator_id, validator_address, commission_rate FROM validators"
    validators = db_manager.execute_query(query)

    for validator in validators:
        validator_id, validator_address, old_commission_rate = validator
        metadata_result = fetch_validator_metadata(validator_address)

        if metadata_result.success:
            new_metadata = metadata_result.data
            new_commission_rate = new_metadata['commission_rate']
            commission_rate_changed = str(new_commission_rate) != str(old_commission_rate)
            update_data = {
                'email': new_metadata['email'],
                'website': new_metadata['website'],
                'discord_handle': new_metadata['discord_handle'],
                'avatar': new_metadata['avatar'],
                'commission_rate': new_commission_rate,
            }
            conditions = {'validator_id': validator_id}
            db_manager.update_data(conditions, update_data)
            # logger.info(f"Metadata for validator {validator_id} updated successfully.")

            # if commission_rate_changed:
            #     subscribed_users = fetch_subscribed_users(db_manager, validator_id)
            #     notify_users_of_change(subscribed_users, validator_id, 'commission_rate', new_commission_rate)
        else:
            logger.error(f"Failed to fetch metadata for validator {validator_id}: {metadata_result.error}")


def update_status(db_manager):
    query = "SELECT validator_id, validator_address, status FROM validators"
    validators = db_manager.execute_query(query)

    for validator in validators:
        validator_id, validator_address, old_status = validator
        status_result = fetch_validator_state(validator_address)

        if status_result.success:
            new_status = status_result.data
            status_changed = new_status != old_status
            update_data = {'status': new_status}
            conditions = {'validator_id': validator_id}
            db_manager.update_data(conditions, update_data)
            logger.info(f"Status for validator {validator_id} updated to {new_status}.")

            # if status_changed:
            #     subscribed_users = fetch_subscribed_users(db_manager, validator_id)
            #     notify_users_of_change(subscribed_users, validator_id, 'status', new_status)
        else:
            logger.error(f"Failed to fetch status for validator {validator_id}: {status_result.error}")


def notify_users_of_change(subscribed_users, validator_id, change_type, new_value):
    # 通知逻辑
    for user in subscribed_users:
        # 发送通知
        # 这里的实现将根据您选择的通知方式而定
        logger.info(f"Notify user {user} about {change_type} change for validator {validator_id} to {new_value}.")


