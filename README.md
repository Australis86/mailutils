# Email Utilies (mailutils)
Email utilities used by my other projects.

## Dependencies

These scripts are built on Python 2.7.x. The following additional modules are used:

* yaml
* [oauth2](https://github.com/google/gmail-oauth2-tools/wiki/OAuth2DotPyRunThrough) (Google's OAuth2 module)

## Installation and Configuration

After downloading, run `mail.py -c` to generate the configuration file. The user will be able to choose between OAuth2 with Gmail, an ISP relay, smtplib or the ssmtp binary.

## History

* 2016-01-26 Overhauled PVR transfer script and separated email configuration into separate scripts.
* 2018-07-06 Migrated to Github, including historical script versions.
* 2018-11-30 Implementation YAML for the configuration file.

## Copyright and Licence

Unless otherwise stated, these scripts are Copyright © Joshua White and licensed under the GNU Lesser GPL v3.

* `oauth2.py` is Copyright © Google Inc. and licensed under the Apache License Version 2.0.