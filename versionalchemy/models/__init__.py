import logging
from datetime import datetime
import json
from operator import and_

from sqlalchemy import Column, Integer, Boolean, DateTime, func
import sqlalchemy as sa
from sqlalchemy.orm.attributes import InstrumentedAttribute

from versionalchemy import utils
from versionalchemy.exceptions import LogTableCreationError, RestoreError, LogIdentifyError, HistoryItemNotFound
import arrow
log = logging.getLogger(__name__)


class VALogMixin(object):
    """
    A mixin providing the schema for the log table, an append only table which saves old versions
    of rows. An inheriting model must specify the following columns:
      - user_id - a column corresponding to the user that made the specified change
      - 1 or more columns which are a subset of columns in the user table. These columns
      must have a unique constraint on the user table and also be named the same in both tables
    """
    va_id = Column(Integer, primary_key=True, autoincrement=True)
    va_version = Column(Integer, nullable=False, index=True)
    va_deleted = Column(Boolean, nullable=False)
    va_updated_at = Column(DateTime, nullable=False)
    va_data = Column(utils.JSONEncodedDict, nullable=False)  # JSON blob

    @classmethod
    def build_row_dict(cls, ut_row, session, deleted=False, user_id=None, use_dirty=True):
        """
        :param ut_row: the row from the user table
        :param deleted: whether or not the row is deleted
        :param user_id: the user that is performing the update on this row
        :param use_dirty: whether to use the dirty fields from ut_row or not

        :return: a dictionary of key value pairs to be inserted into the archive table
        :rtype: dict
        """
        at_data = {
            'va_deleted': deleted,
            'va_updated_at': datetime.now(),
            'va_data': ut_row._to_dict(utils.get_dialect(session), use_dirty=use_dirty),
        }
        version = cls._latest_version(session, ut_row, use_dirty=use_dirty)
        at_data['va_version'] = 0 if version is None else version + 1
        for col_name in cls._version_col_names:
            at_data[col_name] = utils.get_column_attribute(ut_row, col_name, use_dirty=use_dirty)

        if user_id is not None:
            at_data['user_id'] = user_id

        return at_data

    @classmethod
    def _latest_version(cls, session, row, use_dirty=True):
        """
        :param session: a session instance to execute a select on the log table
        :param row: an instance of the user table row object

        :return: the maximum version ID recorded for the specified row or None if version_id
        has not been inserted
        :rtype: int
        """
        and_clause = \
            utils.generate_and_clause(cls, row, cls._version_col_names, use_dirty=use_dirty)
        result = session.execute(
            sa.select([func.max(cls.va_version)]).
            where(and_clause)
        ).first()
        return None if result is None else result[0]

    @classmethod
    def _validate(cls, engine, *version_cols):
        """
        :param engine: instance of :class:`~sa.engine.Engine`
        :param *version_cols: instances of :class:`~sa.orm.attributes.InstrumentedAttribute` from
        the user table corresponding to the columns that versioning pivots around

        If all of the properties are not met, this function raises :class:`~LogTableCreationError`:
            - all version columns exist in the archive table
            - the python types of the user table and archive table columns are the same
            - a user_id column exists
            - there is a unique constraint on version and the other versioned columns from the
            user table
        """
        cls._version_col_names = set()
        for version_column_ut in version_cols:
            # Make sure all version columns exist on this table
            version_col_name = version_column_ut.key
            version_column_at = getattr(cls, version_col_name, None)
            if not isinstance(version_column_at, sa.orm.attributes.InstrumentedAttribute):
                raise LogTableCreationError(
                    "Log table needs {} column".format(version_col_name)
                )

            # Make sure the type of the user table and log table columns are the same
            version_col_at_t = version_column_at.property.columns[0].type.python_type
            version_col_ut_t = version_column_ut.property.columns[0].type.python_type
            if version_col_at_t != version_col_ut_t:
                raise LogTableCreationError(
                    "Type of column {} must match in log and user table".format(version_col_name)
                )
            cls._version_col_names.add(version_col_name)

        # Ensure user added a user_id column
        # TODO: should user_id column be optional?
        user_id = getattr(cls, 'user_id', None)
        if not isinstance(user_id, sa.orm.attributes.InstrumentedAttribute):
            raise LogTableCreationError(
                "Log table needs user_id column"
            )

        # Check the unique constraint on the versioned columns
        version_col_names = list(cls._version_col_names) + ['va_version']
        if not utils.has_constraint(cls.__tablename__, engine, *version_col_names):
            raise LogTableCreationError(
                "There is no unique contraint on the version columns"
            )


class VAModelMixin(object):
    va_id = Column(Integer, nullable=False, default=0)

    va_ignore_columns = None
    va_version_columns = None

    def updated_by(self, user):
        self._updated_by = user

    @classmethod
    def register(cls, ArchiveTable, engine):
        """
        :param ArchiveTable: the model for the users archive table
        :param engine: the database engine
        :param version_col_names: strings which correspond to columns that versioning will pivot \
            around. These columns must have a unique constraint set on them.
        """
        version_col_names = cls.va_version_columns
        if not version_col_names:
            raise LogTableCreationError('Need to specify version cols in cls.va_version_columns')
        if cls.va_ignore_columns is None:
            cls.va_ignore_columns = set()
        cls.va_ignore_columns.add('va_id')
        version_cols = [getattr(cls, col_name, None) for col_name in version_col_names]

        cls._validate(engine, *version_cols)

        ArchiveTable._validate(engine, *version_cols)
        cls.ArchiveTable = ArchiveTable

    def _to_dict(self, dialect, use_dirty=True):
        """
        :param dialect: a :py:class:`~sqlalchemy.engine.interfaces.Dialect` corresponding to the \
            SQL dialect being used.
        :param use_dirty: whether to make a dict of the fields as they stand, or the fields \
            before the row was updated

        :return: a dictionary of key value pairs representing this row.
        :rtype: dict
        """
        return {
            cn: utils.get_column_attribute(self, c, use_dirty=use_dirty, dialect=dialect)
            for c, cn in utils.get_column_keys_and_names(self)
            if c not in self.va_ignore_columns
        }

    @classmethod
    def _validate(cls, engine, *version_cols):
        version_col_names = set()
        for version_column_ut in version_cols:
            if not isinstance(version_column_ut, sa.orm.attributes.InstrumentedAttribute):
                raise LogTableCreationError(
                    "All version columns must be <sa.orm.attributes.InstrumentedAttribute>"
                )
            version_col_names.add(version_column_ut.key)

        # Check the unique constraint on the versioned columns
        insp = sa.inspect(cls)
        uc = sorted([col.name for col in insp.primary_key]) == sorted(version_col_names)
        if not (uc or utils.has_constraint(cls.__tablename__, engine, *version_col_names)):
            raise LogTableCreationError(
                "There is no unique contraint on the version columns"
            )

    def version(self, session):
        """
        Returns the rows current version. This can only be called after a row has been
        inserted into the table and the session has been flushed. Otherwise this
        method has undefined behavior.
        """
        result = session.execute(
            sa.select([self.ArchiveTable.va_version]).
            where(self.ArchiveTable.va_id == self.va_id)
        ).first()
        return result[0]

    @classmethod
    def create_log_select_expression(cls, attributes):
        expressions = ()
        for col_name in cls.ArchiveTable._version_col_names:
            if col_name not in attributes:
                raise LogIdentifyError("Can't determine item id - no parameters passed, "
                                       "please pass '{}' argument".format(col_name))

            expressions += (getattr(cls.ArchiveTable, col_name) == attributes[col_name],)

        if len(expressions) > 1:
            return and_(expressions)

        return expressions[0]

    @classmethod
    def va_list_by_pk(cls, session, **kwargs):
        """
        Returns all VA version id's of this record with there corresponding user_id.
        This can be called after a row has been inserted into the table and the session has been flushed.
        """
        return utils.result_to_dict(session.execute(
            sa.select([cls.ArchiveTable.va_id, cls.ArchiveTable.user_id, cls.ArchiveTable.va_version])
            .where(cls.create_log_select_expression(kwargs))
        ))

    def get_row_identifier(self):
        return {
            col_name: getattr(self, col_name) for col_name in self.ArchiveTable._version_col_names
        }

    def va_list(self, session):
        """
        Returns all VA version id's of this record with there corresponding user_id.
        This can be called after a row has been inserted into the table and the session has been flushed.
        :param session: flushed session
        :return: a list of dicts with va_id and user_id as keys and their values
        :rtype: list
        """
        return self.va_list_by_pk(session, **self.get_row_identifier())

    @classmethod
    def va_get(cls, session, va_version=None, va_id=None):
        """
        Returns historic object (log record). Provide one of va_version, va_id to identify version
        This can be called after a row has been inserted into the table and the session has been flushed.
        :param session: flushed session
        :param va_version - va_version of log row (va_version field in va_version)
        :param va_id: va_id of requested record (va_id field). Can be used as alternative to va_version
        :return: a dictionary of key value pairs representing version id, id of the record in model,
         and versioned model's data
        :rtype: dict
        """
        if va_version is not None and va_id is not None:
            log.warning("both va_version and va_id provided, only va_version will be used, please exclude one of them "
                        "from call")

        if va_version is None and va_id is None:
            raise LogIdentifyError("Please provide at least one from va_version, va_id to identify column")

        if va_version is not None:
            filter_condition = (cls.ArchiveTable.va_version == va_version,)
        else:
            filter_condition = (cls.ArchiveTable.va_id == va_id,)

        result = utils.result_to_dict(session.execute(
                sa.select({cls.ArchiveTable.va_id, cls.ArchiveTable.va_data})
                .where(*filter_condition)
        ))

        if not len(result):
            if va_version is not None:
                identify_str = 'va_version={}'.format(va_version)
            else:
                identify_str = 'va_id={}'.format(va_id)
            raise HistoryItemNotFound("Can't find log record by {}".format(identify_str))

        result = result[0]
        historic_object = result['va_data']
        historic_object['va_id'] = result['va_id']
        return historic_object

    @classmethod
    def va_restore(cls, session, va_version=None, va_id=None):
        """
        Restores historic object. Provide one of va_version, va_id to identify version
        If column was  not included in older version, then it should be nullable. \
        This method will set new value to null. Otherwise, it rases exception.
        :param session: flushed session
        :param va_version - va_version of log row to restore (va_version field in va_version)
        :param va_id: va_id of record to restore (va_id field). Can be used as alternative to va_version
        :return: None
        """
        vals = cls.va_get(session, va_version, va_id)
        row = session.query(cls).get(vals['id'])
        values = {}
        for col_name, model_column in cls.__dict__.items():
            if type(model_column) is not InstrumentedAttribute:
                continue
            if col_name in vals:
                values[col_name] = vals.get(col_name)
                if values[col_name] is not None and getattr(cls, col_name).type.python_type is datetime:
                    values[col_name] = arrow.get(vals[col_name]).datetime
            else:
                if getattr(model_column, 'nullable', None) is not None:
                    if model_column.nullable:
                        values[col_name] = None
                        log.warning("Model '{}' has new column '{}' which has no default, using NULL".format(
                            cls.__name__, col_name))
                    else:
                        raise RestoreError(
                            ("We does not support non-nullable values that were added in new version of model"
                             "'{}'. New column is '{}', please mark it as nullable to be able to restore").format(
                                cls.__name__, col_name))
        if row is None:
            session.execute(sa.insert(cls).values(values))
        else:
            for col_name, col_value in values.items():
                setattr(row, col_name, col_value)
        session.flush()
        session.commit()

    @classmethod
    def va_diff(cls, session, va_version=None, va_id=None):
        """
        Compares version identified by 'va_version' or 'va_id' with previous version.
        Provide one of va_version, va_id
        :param session: flushed session
        :param va_id: version id of log row to be compared
        :return: dict with versions, user_id's and dict with columns as keys and changes as values
        :return: dict
        """
        if va_version is not None and va_id is not None:
            log.warning("both va_version and va_id provided, only va_version will be used, please exclude one of them "
                        "from call")

        if va_version is None and va_id is None:
            raise LogIdentifyError("Please provide at least one from va_version, va_id to identify column")

        if va_version is not None:
            filter_condition = (cls.ArchiveTable.va_version == va_version,)
        else:
            filter_condition = (cls.ArchiveTable.va_id == va_id,)

        this_row = utils.result_to_dict(session.execute(
            sa.select({cls.ArchiveTable}).where(*filter_condition)
        ))
        if not len(this_row):
            if va_version is not None:
                identify_str = 'va_version={}'.format(va_version)
            else:
                identify_str = 'va_id={}'.format(va_id)
            raise HistoryItemNotFound("Can't find log record by {}".format(identify_str))
        this_row = this_row[0]

        va_id = this_row['va_id']
        all_history_items = {
           col_name: this_row[col_name] for col_name in cls.ArchiveTable._version_col_names
        }
        prev_log = [
            log for log in cls.va_list_by_pk(session, **all_history_items) if log['va_id'] < va_id
        ]
        if not prev_log:
            return utils.compare_rows(None, this_row)

        prev_va_id = prev_log[-1]['va_id']
        prev_row = utils.result_to_dict(session.execute(
                sa.select({cls.ArchiveTable})
                .where(cls.ArchiveTable.va_id == prev_va_id)
        ))[0]

        return utils.compare_rows(prev_row, this_row)

    def va_diff_all(self, session):
        return self.va_diff_all_by_pk(session, **self.get_row_identifier())

    @classmethod
    def va_diff_all_by_pk(cls, session, **kwargs):
        all_history_items = utils.result_to_dict(session.execute(
            sa.select([cls.ArchiveTable])
                .where(cls.create_log_select_expression(kwargs))
        ))
        all_changes = []
        for i in range(len(all_history_items)):
            if i is 0:
                all_changes.append(utils.compare_rows(None, all_history_items[i]))
            else:
                all_changes.append(utils.compare_rows(all_history_items[i-1], all_history_items[i]))

        return all_changes

    @classmethod
    def va_get_all_by_pk(cls, session, **kwargs):
        all_history_items = utils.result_to_dict(session.execute(
            sa.select([
                cls.ArchiveTable.va_id,
                cls.ArchiveTable.va_version,
                cls.ArchiveTable.user_id,
                cls.ArchiveTable.va_data.label('record')
            ]).where(
                cls.create_log_select_expression(kwargs))
        ))
        return all_history_items

    def va_get_all(self, session):
        return self.va_get_all_by_pk(session, **self.get_row_identifier())
