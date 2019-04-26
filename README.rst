
VersionAlchemy
==============
A library built on top of the SQLAlchemy ORM for versioning 
row changes to relational SQL tables.

Authors: `Ryan Kirkman <https://www.github.com/ryankirkman/>`_ and
`Akshay Nanavati <https://www.github.com/akshaynanavati/>`_

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
    
    import versionalchemy as va
    from versionalchemy.models import VAModelMixin, VALogMixin

    MY_SQL_URL = '<insert mysql url here>'
    engine = create_engine(MY_SQL_URL)
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
    
    va.init()  # Only call this once
    Example.register(ExampleArchive, engine)  # Call this once per engine, AFTER va.init

Model methods
----------------
va_list(session)
^^^^^^^^^^^^^^^^
Return all VA version id's of this record with there corresponding user_id.

Call: *model.va_list(session)*

Proposed return object:

.. code-block:: python

	[
		{'va_id': 1, 'user_id': 1, 'va_updated_at': '2019-04-12 10:19:34'},
		{'va_id': 2, 'user_id': 1, 'va_updated_at': '2019-04-12 10:30:35'},
		{'va_id': 3, 'user_id': 2, 'va_updated_at': '2019-04-12 10:40:34'}
	]

va_get(session, va_id)
^^^^^^^^^^^^^^^^^^^^^^
Return (historic) object.

Call: *model.va_get(session, 23)*

Proposed return object

.. code-block:: python

    {
        'va_id': 23,
        'id': 4,
        'column1': 'something',
        'column2': 'somethingElse'
    }

va_restore(session, va_id)
^^^^^^^^^^^^^^^^^^^^^^^^^^
Restore historic object.

Call: *model.va_restore(session, 23)*


- A restore is an UPDATE statement (ORM save) thus no DELETION / INSERT
- A restrore is logged as new change in the table.
- Log a warning when you restore a record with more or less columns then the current table schema.
- When a historic record's column is missing, set this field to NULL.
- !If column was  not included in older version, then it should be nullable. 'Restore' will set new value to null.
- Raises exception if fails.Return (historic) object.


va_diff(session, va_id)
~~~~~~~~
Compare `va_id` with previous value.
Call: `model.va_diff(session, 23)`
Show difference between two sequential id's:

Assume:

column      row example 1   row example 2
user_id     1               2
va_version  0               1
va_updated_at|2019-04-12 10:19:34|2019-04-12 10:21:34
|
id|1|1
column1|sunshine|sunshine
column2|foo|bar
column3|NULL|ball
<del>column4</del>|old|-
column5|-|new_field

Example output:

``` python3
{
    'va_prev_version': 0,
    'va_version': 1,
    'va_updated_at': '2019-04-12 10:21:34',
    'user_id': 2,
    'change': {
        'column2': {
            'prev': 'foo',
            'this': 'bar'
        },
        'column3': {
            'prev': None,
            'this': 'ball'
        },
        'column4': {
            'prev': 'old',
            'this': None
        },
        'column5': {
            'prev': None,
            'this': 'new_field'
        }
    }
}
```

### va\_diff\_all()

Return differences between all version of a certain record.

Implementation idea: https://stackoverflow.com/a/47433207
In our case we might not want to have "add" and "remove" since the dict structure (mysql column's) are rather fixed.

Assume:

column|row example 1|row example 2|row example 3
---|---|---|---
user_id|1|2|2
va_version|0|1|2
va_updated_at|2019-04-12 10:19:34|2019-04-12 10:21:34
|
id|1|1|1
column1|sunshine|sunshine|sunshine
column2|foo|bar|bar
column3|NULL|ball|game
<del>column4</del>|old|-|-
column5|-|new_field|new_field

Example output:

``` python3
{
	[
		'va_prev_version': None,
		'va_version': 0,
		'va_updated_at': '2019-04-12 10:19:34',
		'user_id': 2,
		'change': {
			'id': {
				'prev': None,
				'this': 1
			},
			'column1': {
				'prev': None,
				'this': 'sunshine'
			},
			'column2': {
				'prev': None,
				'this': 'foo'
			},
			'column4': {
				'prev': None,
				'this': 'old'
			}
		}
	],
	[
		'va_prev_version': 0,
		'va_version': 1,
		'va_updated_at': '2019-04-12 10:21:34',
		'user_id': 2,
		'change': {
			'column2': {
				'prev': 'foo',
				'this': 'bar'
			},
			'column3': {
				'prev': None,
				'this': 'ball'
			},
			'column4': {
				'prev': 'old',
				'this': None
			},
			'column5': {
				'prev': None,
				'this': 'new_field'
			}
		}
	],
	[
		'va_prev_version': 1,
		'va_version': 2,
		'user_id': 2,
		'change': {
			'column3': {
				'prev': 'ball',
				'this': 'game'
			}
		}
	],
}
```

### va\_get\_all()

Return all version of a certain record.

Assume:

column|row example 1|row example 2|row example 3
---|---|---|---
user_id|1|2|2
va_version|0|1|2
va_updated_at|2019-04-12 10:19:34|2019-04-12 10:21:34|2019-04-13 10:28:34
|
id|1|1|1
column1|sunshine|sunshine|sunshine
column2|foo|bar|bar
column3|NULL|ball|game
<del>column4</del>|old|-|-
column5|-|new_field|new_field

Example output:

``` python3
{
	[
		'va_version': 0,
		'va_updated_at': '2019-04-12 10:19:34',
		'user_id': 1,
		'record': {
			'id': 1,
			'column1': 'sunshine',
			'column2': 'foo',
			'column3': None,
			'column4': 'old'
		}
	],
	[
		'va_version': 1,
		'va_updated_at': '2019-04-12 10:21:34',
		'user_id': 2,
		'record': {
			'id': 1,
			'column1': 'sunshine',
			'column2': 'bar',
			'column3': 'ball',
			'column5': 'new_field'
		}
	],
	[
		'va_version': 2,
		'va_updated_at': '2019-04-13 10:28:34',
		'user_id': 2,
		'record': {
			'id': 1,
			'column1': 'sunshine',
			'column2': 'bar',
			'column3': 'game',
			'column5': 'new_field'
		}
	]
}
```


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
