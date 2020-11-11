#!/usr/bin/env python

from enum import Enum
import logging
from os.path import join
from sqlalchemy import (
    create_engine,
    inspect,
    MetaData,
)
from sqlalchemy.engine.base import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import (
    sessionmaker,
    Session,
    Query
)
from sqlalchemy.schema import DropConstraint, ForeignKeyConstraint, Table
from typing import Optional
from hummingbot.client.config.global_config_map import global_config_map
from hummingbot import data_path
from hummingbot.logger.logger import HummingbotLogger
from . import get_declarative_base
from .metadata import Metadata as LocalMetadata


class SQLSessionWrapper:
    def __init__(self, session: Session):
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._session.commit()
        else:
            self._session.rollback()


class SQLConnectionType(Enum):
    TRADE_FILLS = 1


class SQLConnectionManager:
    _scm_logger: Optional[HummingbotLogger] = None
    _scm_trade_fills_instance: Optional["SQLConnectionManager"] = None

    LOCAL_DB_VERSION_KEY = "local_db_version"
    LOCAL_DB_VERSION_VALUE = "20190614"

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._scm_logger is None:
            cls._scm_logger = logging.getLogger(__name__)
        return cls._scm_logger

    @classmethod
    def get_declarative_base(cls):
        return get_declarative_base()

    @classmethod
    def get_trade_fills_instance(cls, db_name: Optional[str] = None) -> "SQLConnectionManager":
        if cls._scm_trade_fills_instance is None:
            cls._scm_trade_fills_instance = SQLConnectionManager(SQLConnectionType.TRADE_FILLS, db_name=db_name)
        elif cls.create_db_path(db_name=db_name) != cls._scm_trade_fills_instance.db_path:
            cls._scm_trade_fills_instance.commit()
            cls._scm_trade_fills_instance = SQLConnectionManager(SQLConnectionType.TRADE_FILLS, db_name=db_name)
        return cls._scm_trade_fills_instance

    @classmethod
    def create_db_path(cls, db_path: Optional[str] = None, db_name: Optional[str] = None) -> str:
        if db_path is not None:
            return db_path
        if db_name is not None:
            return join(data_path(), f"{db_name}.sqlite")
        else:
            return join(data_path(), "hummingbot_trades.sqlite")

    @classmethod
    def get_db_engine(cls,
                      dialect: str,
                      params: dict) -> Engine:
        # Fallback to `sqlite` if dialect is None
        if dialect is None:
            dialect = "sqlite"

        if "sqlite" in dialect:
            db_path = params.get("db_path")

            return create_engine(f"{dialect}:///{db_path}")
        else:
            username = params.get("db_username")
            password = params.get("db_password")
            host = params.get("db_host")
            port = params.get("db_port")
            db_name = params.get("db_name")

            return create_engine(f"{dialect}://{username}:{password}@{host}:{port}/{db_name}")

    def __init__(self,
                 connection_type: SQLConnectionType,
                 db_path: Optional[str] = None,
                 db_name: Optional[str] = None):
        db_path = self.create_db_path(db_path, db_name)
        self.db_path = db_path

        engine_options = {
            "db_engine": global_config_map.get("db_engine").value,
            "db_host": global_config_map.get("db_host").value,
            "db_port": global_config_map.get("db_port").value,
            "db_username": global_config_map.get("db_username").value,
            "db_password": global_config_map.get("db_password").value,
            "db_name": global_config_map.get("db_name").value,
            "db_path": db_path
        }

        if connection_type is SQLConnectionType.TRADE_FILLS:
            self._engine: Engine = self.get_db_engine(
                engine_options.get("db_engine"),
                engine_options)
            self._metadata: MetaData = self.get_declarative_base().metadata
            self._metadata.create_all(self._engine)

            # SQLite does not enforce foreign key constraint, but for others engines, we need to drop it.
            # See: `hummingbot/market/markets_recorder.py`, at line 213.
            with self._engine.begin() as conn:
                inspector = inspect(conn)

                for tname, fkcs in reversed(
                        inspector.get_sorted_table_and_fkc_names()):
                    if fkcs:
                        if not self._engine.dialect.supports_alter:
                            continue
                        for fkc in fkcs:
                            fk_constraint = ForeignKeyConstraint((), (), name=fkc)
                            Table(tname, MetaData(), fk_constraint)
                            conn.execute(DropConstraint(fk_constraint))

        self._session_cls = sessionmaker(bind=self._engine)
        self._shared_session: Session = self._session_cls()

        if connection_type is SQLConnectionType.TRADE_FILLS:
            self.check_and_upgrade_trade_fills_db()

    @property
    def engine(self) -> Engine:
        return self._engine

    def get_shared_session(self) -> Session:
        return self._shared_session

    def check_and_upgrade_trade_fills_db(self):
        try:
            query: Query = (self._shared_session.query(LocalMetadata)
                            .filter(LocalMetadata.key == self.LOCAL_DB_VERSION_KEY))
            result: Optional[LocalMetadata] = query.one_or_none()

            if result is None:
                version_info: LocalMetadata = LocalMetadata(key=self.LOCAL_DB_VERSION_KEY,
                                                            value=self.LOCAL_DB_VERSION_VALUE)
                self._shared_session.add(version_info)
                self._shared_session.commit()
            else:
                # There's no past db version to upgrade from at this moment. So we'll just update the version value
                # if needed.
                if result.value < self.LOCAL_DB_VERSION_VALUE:
                    result.value = self.LOCAL_DB_VERSION_VALUE
                    self._shared_session.commit()
        except SQLAlchemyError:
            self.logger().error("Unexpected error while checking and upgrading the local database.",
                                exc_info=True)

    def commit(self):
        self._shared_session.commit()

    def begin(self) -> SQLSessionWrapper:
        return SQLSessionWrapper(self._session_cls())
