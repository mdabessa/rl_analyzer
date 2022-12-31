import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

from random import shuffle
from src.db import database

collection_name = 'ranked-doubles'
prop = 1/7

collection = database.get_collection(collection_name)

data = list(collection.find({}))
print(f'Found {len(data)} replays')
shuffle(data)

test = data[:int(len(data) * prop)]
train = data[int(len(data) * prop):]

c_test = database.get_collection(f'{collection_name}-test')
c_train = database.get_collection(f'{collection_name}-train')

c_test.drop()
c_train.drop()

for replay in test:
    if c_test.find_one({'id': replay['id']}) is None:
        c_test.insert_one(replay)

for replay in train:
    if c_train.find_one({'id': replay['id']}) is None:
        c_train.insert_one(replay)
    