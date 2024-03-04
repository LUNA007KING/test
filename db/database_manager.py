import logging
import mysql.connector
from mysql.connector import errorcode

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class DatabaseManager:
    def __init__(self, db_config):
        self.db_config = db_config
        self._database = db_config.get('database', None)
        self._table_name = ''
        self._columns = {}

    @property
    def database(self):
        return self._database

    @database.setter
    def database(self, value):
        if not value:
            raise ValueError("Database name cannot be empty.")
        self._database = value
        self.db_config['database'] = value

    @property
    def table_name(self):
        return self._table_name

    @table_name.setter
    def table_name(self, value):
        if not value:
            raise ValueError("Table name cannot be empty.")
        self._table_name = value

    @property
    def columns(self):
        return self._columns

    @columns.setter
    def columns(self, value):
        if not isinstance(value, dict) or not value:
            raise ValueError("Columns must be a non-empty dictionary.")
        self._columns = value

    def connect(self, include_db=True):
        config = self.db_config.copy()
        if not include_db:
            config.pop('database', None)
        try:
            return mysql.connector.connect(**config)
        except mysql.connector.Error as err:
            logger.error(f"Database connection error: {err}")
            raise

    def execute_query(self, query, params=None, commit=False):
        try:
            with self.connect() as conn, conn.cursor() as cursor:
                cursor.execute(query, params)
                if commit:
                    conn.commit()
                else:
                    return cursor.fetchall()
        except mysql.connector.Error as err:
            logger.error(f"Error executing query: {err}")
            raise

    def create_database(self):
        if not self._database:
            raise ValueError("Database name must be set before creating the database.")
        query = f"CREATE DATABASE IF NOT EXISTS `{self._database}` DEFAULT CHARACTER SET 'utf8'"
        try:
            with self.connect(include_db=False) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    conn.commit()
            logger.info(f"Database {self._database} created successfully.")
        except mysql.connector.Error as err:
            logger.error(f"Failed to create database {self._database}: {err}")
            raise

    def create_table(self, foreign_keys=None):
        if not self._table_name or not self._columns:
            raise ValueError("Table name and columns must be specified.")
        try:
            with self.connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"SHOW TABLES LIKE '{self._table_name}'")
                    if cursor.fetchone():
                        logger.info(f"Table {self._table_name} already exists.")
                        return
                    columns_definitions = ", ".join(
                        [f"`{column}` {properties}" for column, properties in self._columns.items()])
                    if foreign_keys:
                        fk_definitions = ", ".join(foreign_keys)
                        columns_definitions += ", " + fk_definitions
                    query = f"CREATE TABLE `{self._table_name}` ({columns_definitions}) ENGINE=InnoDB"
                    cursor.execute(query)
                    logger.info(f"Table {self._table_name} created successfully.")
        except mysql.connector.Error as err:
            logger.error(f"Error creating table {self._table_name}: {err}")
            raise

    def insert_data(self, data):
        try:
            columns = ', '.join([f"`{col}`" for col in data.keys()])
            placeholders = ', '.join(['%s'] * len(data))
            query = f"INSERT INTO `{self.table_name}` ({columns}) VALUES ({placeholders})"
            self.execute_query(query, tuple(data.values()), commit=True)
            logger.info(f"Data inserted successfully into {self.table_name}.")
        except mysql.connector.Error as err:
            logger.error(f"Failed to insert data into {self.table_name}: {err}")
            raise

    def update_data(self, conditions, updates):
        set_clause = ', '.join([f"`{column}` = %s" for column in updates])
        where_clause = ' AND '.join([f"`{field}` = %s" for field in conditions])
        query = f"UPDATE `{self.table_name}` SET {set_clause} WHERE {where_clause}"
        params = tuple(updates.values()) + tuple(conditions.values())

        try:
            with self.connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    conn.commit()  # 确保提交事务
                    if cursor.rowcount == 0:
                        # logger.info("No rows updated (the target data may not exist).")
                        return False, 0  # 返回一个表示未更新任何行的标志和行数
                    else:
                        logger.info(f"{cursor.rowcount} row(s) updated successfully.")
                        return True, cursor.rowcount  # 返回成功标志和更新的行数
        except mysql.connector.Error as err:
            logger.error(f"Failed to update data in {self.table_name}: {err}")
            return False, 0  # 在异常情况下返回失败标志和0行被更新

    def delete_data(self, conditions):
        where_clause = ' AND '.join([f"`{field}` = %s" for field in conditions])
        query = f"DELETE FROM `{self.table_name}` WHERE {where_clause}"
        params = tuple(conditions.values())

        try:
            with self.connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    conn.commit()  # Ensure the transaction is committed
                    if cursor.rowcount == 0:
                        logger.info("No rows deleted (the target data may not exist).")
                        return False, 0  # Return an indication that no rows were deleted
                    else:
                        logger.info(f"{cursor.rowcount} row(s) deleted successfully.")
                        return True, cursor.rowcount  # Return success flag and number of rows deleted
        except mysql.connector.Error as err:
            logger.error(f"Failed to delete data from {self.table_name}: {err}")
            return False, 0