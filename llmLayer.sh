mkdir -p llmLayer/python
pip install --platform manylinux2014_x86_64 --target llmLayer/python --python-version 3.12 --only-binary=:all: numpy
pip install --platform manylinux2014_x86_64 --target llmLayer/python --python-version 3.12 --only-binary=:all: boto3
pip install --platform manylinux2014_x86_64 --target llmLayer/python --python-version 3.12 --only-binary=:all: langchain
pip install --platform manylinux2014_x86_64 --target llmLayer/python --python-version 3.12 --only-binary=:all: langchain-community
#cd llmLayer && zip ../llmLayer.zip * -r