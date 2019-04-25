from tests.models import (
    UserTable,
)
from tests.utils import (
    SQLiteTestBase,
)


class TestRestore(SQLiteTestBase):
    def test_restore_row_with_new_nullable_column(self):
        p = UserTable(**self.p1)
        self._add_and_test_version(p, 0)
        p = self.session.query(UserTable).get(p.id)
        first_version = p.va_id
        p.col1 = 'test'
        p.col2 = 10
        self.session.commit()
        p = self.session.query(UserTable).get(p.id)
        self.assertEqual(p.col1, 'test')
        self.assertEqual(p.col2, 10)
        self.assertEqual(p.va_id, first_version + 1, 'Version should be increased')
        self.addTestNullableColumn()
        p = self.session.query(UserTable).get(p.id)
        p.va_restore(self.session, first_version)
        p = self.session.query(UserTable).get(p.id)
        self.assertEqual(p.col1, self.p1['col1'])
        self.assertEqual(p.col2, self.p1['col2'])
        self.assertEqual(p.test_column1, None)
        self.assertEqual(p.va_id, first_version + 2)

    def test_restore_row_with_non_default_column(self):
        p = UserTable(**self.p1)
        self._add_and_test_version(p, 0)
        p = self.session.query(UserTable).get(p.id)
        first_version = p.va_id
        p.col1 = 'test'
        self.session.commit()
        p = self.session.query(UserTable).get(p.id)
        self.assertEqual(p.col1, 'test')
        self.assertEqual(p.va_id, first_version + 1, 'Version should be increased')
        self.addTestNoDefaultNoNullColumn()
        p = self.session.query(UserTable).get(p.id)

        with self.assertRaises(Exception):
            p.va_restore(self.session, first_version)


class TestList(SQLiteTestBase):
    def test_va_list_by_pk(self):
        p = UserTable(**self.p1)
        self._add_and_test_version(p, 0)
        p = self.session.query(UserTable).get(p.id)
        first_version = p.va_id
        p.col1 = 'test'
        self.session.commit()
        res = UserTable.va_list_by_pk(self.session, product_id=p.product_id)

    def test_va_list(self):
        p = UserTable(**self.p1)
        self._add_and_test_version(p, 0)
        p = self.session.query(UserTable).get(p.id)
        first_version = p.va_id
        p.col1 = 'test'
        self.session.commit()
        res = p.va_list(self.session)
