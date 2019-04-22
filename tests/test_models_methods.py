from tests.models import (
    UserTable,
)
from tests.utils import (
    SQLiteTestBase,
)
import versionalchemy

class TestRestore(SQLiteTestBase):
    def test_restore_row_with_same_columns(self):
        p = UserTable(**self.p1)
        self._add_and_test_version(p, 0)
        #new_p = self.session.query(self).get(p.)
        #self.addTestColumn()
        print('P IS', p.__table__.c)
        p.va_restore(self.session, p.va_id)


