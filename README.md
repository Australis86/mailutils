# Email Utilies (mailutils)
Email utilities used by my other projects.

## Dependencies

These scripts are built on Python 3.x. The following additional modules are used:

* PyYAML 6+
* [oauth2](https://github.com/google/gmail-oauth2-tools/wiki/OAuth2DotPyRunThrough) (Google's OAuth2 module)

## Installation and Configuration

After downloading, run `mail.py -c` to generate the configuration file. The user will be able to choose between OAuth2 with Gmail, an ISP relay, smtplib or the ssmtp binary. To use Gmail app passwords, select the smtplib option.

## History

* 2016-01-26 Overhauled PVR transfer script and separated email configuration into separate scripts.
* 2018-07-06 Migrated to Github, including historical script versions.
* 2018-11-30 Implementation YAML for the configuration file.
* 2023-11-17 Updated to Python 3.

## Copyright and Licence

Unless otherwise stated, these scripts are Copyright © Joshua White and licensed under the GNU Lesser GPL v3.

* `oauth2.py` is Copyright © Google Inc. and licensed under the Apache License Version 2.0.
