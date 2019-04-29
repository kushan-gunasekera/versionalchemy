
VersionAlchemy
==============
A library built on top of the SQLAlchemy ORM for versioning 
row changes to relational SQL tables.

Authors: `Ryan Kirkman <https://www.github.com/ryankirkman/>`_ and
`Akshay Nanavati <https://www.github.com/akshaynanavati/>`_

Tested on Python 3.7 and python 2.7 with SQLAlchemey v1.3.3

Build Status
------------
.. image:: https://travis-ci.org/NerdWalletOSS/versionalchemy.svg?branch=master
    :target: https://travis-ci.org/NerdWalletOSS/versionalchemy
    
.. image:: https://readthedocs.org/projects/versionalchemy/badge/?version=latest
    :target: http://versionalchemy.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

Useful Links
------------
- `Developer Documentation <http://versionalchemy.readthedocs.io/en/latest/>`_
- `Blog Post <https://www.nerdwallet.com/blog/engineering/versionalchemy-tracking-row-changes/>`_
  with more in depth design decisions

Getting Started
---------------

.. code-block:: bash

  $ pip install versionalchemy
  
Sample Usage
~~~~~~~~~~~~

.. code-block:: python
    
    import sqlalchemy as sa
    from sqlalchemy import create_engine
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.schema import UniqueConstraint
    from sqlalchemy.orm import Session

    import versionalchemy as va
    from versionalchemy.models import VAModelMixin, VALogMixin

    MY_SQL_URL = '<insert mysql url here>'
    engine = create_engine(MY_SQL_URL)
    session = Session(bind=engine)
    Base = declarative_base(bind=engine)

    class Example(Base, VAModelMixin):
        __tablename__ = 'example'
        va_version_columns = ['id']
        id = sa.Column(sa.Integer, primary_key=True)
        value = sa.Column(sa.String(128))


    class ExampleArchive(Base, VALogMixin):
        __tablename__ = 'example_archive'
        __table_args__ = (
            UniqueConstraint('id', 'va_version'),
        )
        id = sa.Column(sa.Integer)
        user_id = sa.Column(sa.Integer)

    Base.metadata.create_all(engine) # if you need create database tables from models.
    # Otherwise you could use e.g. Alembic for migrating database, or create models manually

    va.init()  # Only call this once
    Example.register(ExampleArchive, engine)  # Call this once per engine, AFTER va.init

Model methods
----------------

Assume we create a new model:

.. code-block:: python

    item = Example(value='initial') 
    item._updated_by = 'user_id_1'  # you can use integer user identifier here from your authorized user model, for versionalchemey it is just a tag
    session.add(item)
    session.commit()  


This will add first version in **example_archive** table and sets **va_id** on instance, e.g.

.. code-block:: python

    item = session.query(Example).get(item.id)
    print(item.va_id)  # 123


Now we can use **va_list** to show all versions:

.. code-block:: python

    print(item.va_list(session))
    # [
    #		{'va_id': 123, 'user_id': 'user_id_1', va_version: 0},
    # ]


Let's change value:

.. code-block:: python

    item.val = 'changed'
    item._updated_by = 'user_id_2'
    session.commit()
    print(item.va_list(session))
    # [
    #       {'va_id': 123, 'user_id': 'user_id_1', 'va_version': 0},
    #       {'va_id': 124, 'user_id': 'user_id_2', 'va_version': 1},
    # ]

You can get specific version of model using **va_get**:

.. code-block:: python

    item.va_get(session, va_id=123)
    # {
    #  'va_id': 123, 
    #  'id': 1, 
    #  'value': 'initial'    
    # }

You can pass `va_version` instead of `va_id`:

.. code-block:: python

    item.va_get(session, va_version=0)
    item.va_get(session, 0) # or even
    # both return same as code snippet above


You can also get all revisions:

.. code-block:: python

    item.va_get_all(session)
    # [
    #   {
    #     'va_id': 123, 
    #     'id': 1,
    #     'record': {
    #       'value': 'initial'
    #     },
    #     'user_id': 'user_id_1',
    #     'va_version': 0
    #   },
    #   {
    #     'va_id': 124, 
    #     'id': 1,
    #     'record': {
    #       'value': 'changed'
    #     },
    #     'user_id': 'user_id_2',
    #     'va_version': 1
    #   }
    # ]


To check difference betweeen current and previous versions use **va_diff**:

.. code-block:: python

    item.va_diff(session, va_id=124) # or item.va_diff(session, va_version=0)
    # {
    #   'va_prev_version': 1,
    #   'va_version': 2,
    #   'prev_user_id': 'user_id_1',
    #   'user_id': 'user_id_2',
    #   'change': {
    #     'value': {
    #       'prev': 'initial',
    #       'this': 'changed'
    #     }
    #   }
    # }


**va_diff_all** will show you diffs between all versions:


.. code-block:: python

    item.va_diff_all(session)
    # [
    #   {
    #     'va_prev_version': 0,
    #     'va_version': 1,
    #     'prev_user_id': None,
    #     'user_id': 'user_id_1',
    #     'change': {
    #       'value': {
    #         'prev': None,
    #         'this': 'initial'
    #       }
    #     }
    #   },
    #   {
    #     'va_prev_version': 1,
    #     'va_version': 2,
    #     'prev_user_id': 'user_id_1',
    #     'user_id': 'user_id_2',
    #     'change': {
    #       'value': {
    #         'prev': 'initial',
    #         'this': 'changed'
    #       }
    #     }
    #   },
    # ]



You can restore some previous version using **va_restore**:

.. code-block:: python

    item.va_restore(session, va_id=123)  # or item.va_restore(session, va_version=0)
    item = session.query(Example).get(item.id)
    print(item.value)  # initial


Latency
-------
We used `benchmark.py <https://gist.github.com/akshaynanavati/f1e816596d100a33e4b4a9c48099a8b7>`_ to
benchmark the performance of versionalchemy. It times the performance of the SQLAlchemy core, ORM
without VersionAclehmy and ORM with VersionAlchemy for ``n`` inserts (where ``n`` was variable). Some
results are below.

+--------+-----------+----------+----------+
| n      | Core Time | ORM Time | VA Time  |
+========+===========+==========+==========+
| 10000  | 9.81 s    | 16.04 s  | 36.13    |
+--------+-----------+----------+----------+
| 100000 | 98.78 s   | 158.87 s | 350.84 s |
+--------+-----------+----------+----------+

VersionAlchemy performs roughly 2 times as bad as the ORM, which makes sense as we are doing roughly one
additional insert per orm insert into the archive table.

Contributing
------------
- Make sure you have `pip <https://pypi.python.org/pypi/pip>`_
  and `virtualenv <https://virtualenv.pypa.io/en/stable/>`_ on your dev machine
- Fork the repository and make the desired changes
- Run ``make install`` to install all required dependencies
- Run ``make lint tests`` to ensure the code is pep8 compliant and  all tests pass.
  Note that the tests require 100% branch coverage to be considered passing
- Open a pull request with a detailed explaination of the bug or feature
- Respond to any comments. The PR will be merged if the travis CI build passes and
  the code changes are deemed sufficient by the admin

Style
~~~~~
- Follow PEP8 with a line length of 100 characters
- Prefer parenthesis to ``\`` for line breaks

License
-------
`MIT License <https://github.com/NerdWalletOSS/versionalchemy/blob/master/LICENSE>`_
