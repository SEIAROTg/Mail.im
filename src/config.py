import os
import yaml

with open(os.path.join(os.path.dirname(__file__), 'config.yml')) as f:
    config = yaml.load(f.read())
