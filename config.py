# Copyright 2015 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This file contains all of the configuration values for the application.
Update this file with the values for your specific Google Cloud project.
You can create and manage projects at https://console.developers.google.com
"""
DEFAULT_AUTHTOKEN = 'vxwxd7J8AlNNFPS8k0a0FfUFtq0ewzFdc'
DEFAULT_SERIAL_SALT = '248f1704b8cc4232b4475143a8e98c32'
DEFAULT_SIGNATURE_SALT = '08f92b7a-7b90-11e6-8b77-86f30ca893d3'

# The secret key is used by Flask to encrypt session cookies.
SECRET_KEY = 'secret'

# There are three different ways to store the data in the application.
# You can choose 'datastore', 'cloudsql', or 'mongodb'. Be sure to
# configure the respective settings for the one you choose below.
# You do not have to configure the other data backends. If unsure, choose
# 'datastore' as it does not require any additional configuration.
DATA_BACKEND = 'datastore'

# Google Cloud Project ID. This can be found on the 'Overview' page at
# https://console.developers.google.com
PROJECT_ID = 'mobivitypassbook-staging'

# Google Cloud Storage and upload settings.
# Typically, you'll name your bucket the same as your project. To create a
# bucket:
#
#   $ gsutil mb gs://<your-bucket-name>
#
# You also need to make sure that the default ACL is set to public-read,
# otherwise users will not be able to see their upload images:
#
#   $ gsutil defacl set public-read gs://<your-bucket-name>
#
# You can adjust the max content length and allow extensions settings to allow
# larger or more varied file types if desired.
CLOUD_STORAGE_BUCKET = 'mobivitypassbook-staging'
MAX_CONTENT_LENGTH = 8 * 1024 * 1024
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])
