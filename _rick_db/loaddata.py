#
# Copyright (c) 2019 MagicStack Inc.
# All rights reserved.
#
# See LICENSE for details.
##


# This file is a placeholder for maintaining consistency with other implementations.
# In the Rick DB implementation, we aren't handling data loading differently from
# the PostgreSQL implementation, so we don't need any special logic here.
#
# The benchmark will use the same PostgreSQL database that was populated by the
# _postgres/loaddata.py script.

print('Rick DB uses the same database as PostgreSQL, no need to load data separately.')
print('If you need to load data, please run: make load-postgres')