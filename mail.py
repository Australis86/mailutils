#!/usr/bin/env python
#-------------------------------------------------------------------------------
# Name:        mail
# Purpose:     Send emails using smtplib. Can use oauth2 to send via Gmail.
#
# Author:      Joshua White
#
# Created:     26/01/2016
# Copyright:   (c) Joshua White 2016-2018
# Licence:     GNU Lesser GPL v3
#-------------------------------------------------------------------------------

'''
In order to use OAuth 2.0, you need to follow the instructions found at:
https://github.com/google/gmail-oauth2-tools/wiki/OAuth2DotPyRunThrough

1. You must register your application through the Google APIs Console:

https://code.google.com/apis/console

2. Use the API Console to create a client id.
3. Enter the client id and client secret into mailConfig.py.
4. Run this script with -i to initialise the tokens. This will automatically 
get the refresh and access tokens, as well as the expiry date and save these.
It will enable automatic regeneration of access tokens.

If you wish to do the steps manually:

4. Create a token:

python oauth2.py --generate_oauth2_token --client_id=ID --client_secret=SECRET

5. Authorise the token.
6. Copy both the access and refresh tokens.
7. Create an OAuth2 authentication string:

python oauth2.py --generate_oauth2_string --access_token=ACCESS_TOKEN --user=USER_EMAIL

8. Test SMTP:

python oauth2.py --test_smtp_authentication --access_token=ACCESS_TOKEN --user=USER_EMAIL

9. Use the authentication string for accessing Gmail.

Note that the access token expires after 1 hour. Your application needs to save 
the refresh token and generate a new access token as required.

Put your Gmail address, client id, client secret and refresh token into mailConfig.py.
Access tokens will be generated every time using this method.
'''


import os
import sys
import errno
import datetime
import shutil
import yaml
import socket
import distutils.spawn
from optparse import OptionParser, OptionGroup

# JSON library
try:
	import json
except ImportError, err:
	import simplejson as json

# MIME type handling
try:
	#Python 2.6+
	from email.mime.multipart import MIMEMultipart
	from email.mime.text import MIMEText
except ImportError, err:
	#Python 2.4
	from email.MIMEMultipart import MIMEMultipart
	from email.MIMEText import MIMEText

########################################
# Sanity checks to see what is available

# Check if Google's OAuth2 module is available
try:
	import oauth2
	useOAuth = True
except ImportError, err:
	useOAuth = False

# Check if smtplib is available
try:
	import smtplib
	useSMTP = True
except ImportError, err:
	useSMTP = False

# If neither Python library is available, fall back to subprocess
if not useSMTP and not useOAuth:
	import subprocess

########################################

# File paths
PATH = os.path.abspath(os.path.dirname(__file__)) # Script directory
SCRIPTNAME = os.path.splitext(os.path.basename(__file__))[0] # Script name
LOGFILE = os.path.join(PATH, '%s.log' % SCRIPTNAME) # Logfile
EMAILFILE = os.path.join(PATH, '%s.email' % SCRIPTNAME) # Temporary storage for email contents
TOKENFILE = os.path.join(PATH, '%s.token' % SCRIPTNAME) # Storage for OAuth2 token
YAMLCONF = os.path.join(PATH, '%s.yaml' % SCRIPTNAME)

# Global variables
opts = None
conf = {}



class DateEncoder(json.JSONEncoder):
	'''Class to extend JSON encoder, courtesy of http://stackoverflow.com/questions/12316638/psycopg2-execute-returns-datetime-instead-of-a-string'''
	def default(self, obj):
		'''Internal function for <DateEncoder>. Converts a datetime object to a string.'''
		if isinstance(obj, datetime.date):
			return obj.strftime('%Y-%m-%d %H:%M:%S') # Do this instead of returning str(obj) to avoid timezone field
		return json.JSONEncoder.default(self, obj)


def logPrint(text):
	'''Print to the screen and write to the log file.'''

	now = datetime.datetime.now()
	nowstr = now.strftime('%Y-%m-%d %H:%M:%S')

	f = open(LOGFILE, 'a')
	f.write('%s\t%s\n' % (nowstr, text))
	f.close()


def initOptions():
	'''System argument processing.'''
	global opts

	usage = "usage: %prog [options]"
	parser = OptionParser(usage=usage)

	parser.add_option("-r", "--recipient",
						dest="recipient", default=None,
						help="Specify the recipient for the email.")
	parser.add_option("-s", "--subject",
						dest="subject", default="No Subject Specified",
						help="Specify the subject string for the email.")
	parser.add_option("-i", "--isp",
					  action="store_true", dest="useISP", default=False,
					  help="Force use of ISP SMTP relay if available.")
	parser.add_option("-t", "--test",
					  action="store_true", dest="test", default=False,
					  help="Send an email using the current configuration.")

	# Options to handle using a file as the source of the email contents
	fileOptions = OptionGroup(parser, "Prepared Email Body Options",
						"These options allow the user to specify a source file for the text and/or HTML part of the email body.")
	fileOptions.add_option("-f", "--file",
						dest="textfile", default=None,
						help="A text file to use for the text part of the email.")
	fileOptions.add_option("-l", "--html",
						dest="htmlfile", default=None,
						help="A HTML file to use for the HTML part of the email.")
	parser.add_option_group(fileOptions)

	# Options to control the configuration script
	configOptions = OptionGroup(parser, "Configuration Options",
						"These options allow the user to create or modify the script configuration.")
	configOptions.add_option("-c", "--configure",
						action="store_true", dest="configure", default=False,
						help="Create a configuration file from the provided template and prompt the user to enter configuration values.")
	configOptions.add_option("-o", "--oauth",
						action="store_true", dest="init_oauth", default=False,
						help="Generate the OAuth tokens. Requires that the initial configuration is complete and the OAuth Client ID and Secret are present in mailConfig.py.")
	parser.add_option_group(configOptions)


	(opts, args) = parser.parse_args()
	return opts, args


def validateKeys(obj, keylist):
	'''Validate that the keys are present in an object and the values are not None.'''
	
	result = True
	for key in keylist:
		result = result and key in obj and obj[key] is not None
	
	return result


def sendEmail(recipient, subject='No Subject Specified', bodytext=None, bodyhtml=None):
	'''Send an email using a configured method. In order of priority, these methods will be used:
		- OAuth2
		- ISP relay
		- smtplib
		- ssmtp'''
	
	# Flags for ISP relay override
	useISP = opts and opts.useISP
	
	# Set the subject and body for test purposes
	if opts and opts.test:
		subject = "Test Email"
		bodytext = "This is a test email."
		logPrint("Preparing to send a test email.")
	
	# Short references to objects
	OA2 = conf['OAuth2']
	ISPr = conf['ISP'] 
	smtpc = conf['smtp']
	userc = conf['user']
	
	# If OAuth2 is enabled...
	if not useISP and useOAuth and validateKeys(OA2,['client_id','client_secret']) and os.path.exists(TOKENFILE):
		# Load the token file
		f = open(TOKENFILE, 'r')
		tokendata = json.load(f)
		expiry = datetime.datetime.strptime(tokendata['expiry'], '%Y-%m-%d %H:%M:%S')
		f.close()
		
		# Check for expired access token
		now = datetime.datetime.now()
		if expiry < now:
			logPrint("Access token expired. Generating a new token.")
			response = oauth2.RefreshToken(OA2['client_id'], OA2['client_secret'], tokendata['refresh'])
			tokendata['access'] = response['access_token']
			tokendata['expiry'] = now + datetime.timedelta(seconds=response['expires_in'])
			
			# Update the saved token data
			f = open(TOKENFILE, 'w')
			json.dump(tokendata, f, cls=DateEncoder)
			f.close()
			
		access_token = tokendata['access']
		
		# Prepare for authentication
		oauth2_string = oauth2.GenerateOAuth2String(conf['user']['sender'], access_token)
		logPrint("Authentication string generated.")
		
		# Set up the connection
		smtp_conn = smtplib.SMTP('smtp.gmail.com', 587)
		if opts and opts.test:
			smtp_conn.set_debuglevel(True)
		smtp_conn.ehlo()
		smtp_conn.starttls()
		smtp_conn.docmd('AUTH', 'XOAUTH2 ' + oauth2_string)
		logPrint("Connected to SMTP server using OAuth.")
	
	# ISP relay fallback
	elif useISP or validateKeys(ISPr,['relay']):
		smtp_conn = smtplib.SMTP(ISPr['relay'])
		logPrint("Connected to SMTP server (ISP relay).")
	
	# smtplib fallback (not recommended)
	elif useSMTP and validateKeys(smtpc,['server','port']):
		# Use mail server
		smtp_conn = smtplib.SMTP(smtpc['server'], smtpc['port'])
		smtp_conn.ehlo()
		if smtpc['starttls']:
			smtp_conn.starttls()
			smtp_conn.ehlo()
			
		smtp_conn.login(smtpc['username'], smtpc['password'])
		logPrint("Connected to SMTP server using account credentials.")

	# Use subprocess and rely on system-configured SSMTP
	else:
		logPrint("Preparing to send email via ssmtp subprocess.")

		# Prepare email header
		email = '''MIME-Version: 1.0\nContent-Type: text/html\nTo: <%s>\nFrom: "%s" <%s>\nReply-To: "%s" <%s>\nSubject: %s\n\n%s''' % (recipient, conf['user']['sender'], conf['user']['sender'], conf['user']['reply-to-name'], conf['user']['reply-to'], subject, bodytext)
		email = email.encode('ascii')

		# Have to write contents to a file. Won't work if you try to echo or cat it.
		f = open(EMAILFILE,'w')
		f.write(email)
		f.close()

		cmdstr = '%s %s < "%s"' % (conf['ssmtp']['path'], recipient, EMAILFILE)
		try:
			subprocess.call(cmdstr, shell=True)
			os.remove(EMAILFILE)
			logPrint('Email sent.')

		except Exception, err:
			logPrint('Error sending email:\n%s' % str(err))
			
		return
	
	# Assemble the email
	msg = MIMEMultipart('alternative')
	msg['From'] = "%s <%s>" % (userc['sender-name'], userc['sender'])
	msg['Reply-To'] = "%s <%s>" % (userc['reply-to-name'], userc['reply-to'])
	msg['To'] = recipient
	msg['Subject'] = subject

	if bodytext is not None:
		textBody = MIMEText(bodytext, 'plain')
		msg.attach(textBody)

	if bodyhtml is not None:
		htmlBody = MIMEText(bodyhtml, 'html')
		msg.attach(htmlBody)

	# Send the email
	smtp_conn.sendmail(userc['sender'], recipient, msg.as_string())
	smtp_conn.close()
	logPrint("Email sent.")


def prepEmail(subject=None, recipient=None, textfile=None, htmlfile=None):
	'''Check for body content to read in and send.'''
	
	bodytext = None
	bodyhtml = None

	# Choose between the arguments to this function and the option parser
	textpath = textfile or (opts and opts.textfile)
	htmlpath = htmlfile or (opts and opts.htmlfile)
	subject = subject or (opts and opts.subject)
	recipient = recipient or (opts and opts.recipient)
	
	# Check if there's a text file to use for the body
	if textpath is not None and os.path.exists(textpath):
		f = open(textpath, 'r')
		bodytext = f.read()
		f.close()
	
	# Check if there's a HTML file to use for the body
	if htmlpath is not None and os.path.exists(htmlpath):
		f = open(htmlpath, 'r')
		bodyhtml = f.read()
		f.close()

	sendEmail(subject=subject, recipient=recipient, bodytext=bodytext, bodyhtml=bodyhtml)


def initialiseOAuth():
	'''Initialise the OAuth token file using the client id and secret.'''
	
	OA2 = conf['OAuth2']
	if useOAuth:
		if validateKeys(OA2, ['client_id', 'client_secret']):
			# Authorise the app
			print 'Visit the following URL to authorise the token:'
			print oauth2.GeneratePermissionUrl(OA2['client_id'], 'https://mail.google.com/')
			print 
			authorisation_code = raw_input('Enter verification code: ')
			
			# Get the access and refresh tokens
			response = oauth2.AuthorizeTokens(OA2['client_id'], OA2['client_secret'], authorisation_code)
			print 'Refresh Token: %s' % response['refresh_token']
			print 'Access Token: %s' % response['access_token']
			
			# Calculate the expiry for the access token
			expiry = datetime.datetime.now() + datetime.timedelta(seconds=response['expires_in'])
			tokendata = {
				'refresh': response['refresh_token'],
				'access': response['access_token'],
				'expiry': expiry,
			}
			
			f = open(TOKENFILE, 'w')
			json.dump(tokendata, f, cls=DateEncoder)
			f.close()
		
		else:
			print "You have not provided a client ID or secret. Please update the configuration file."
	else:
		print "OAuth2 is not enabled. Please install the Google oauth2 module."
	
	
def configureScript():
	'''Initialise the configuration file for the mail script.'''
	
	def updateConfig(obj, key, msg, sys_def=None, castbool=False):
		"""Method to update a configuration field based on user input."""
		
		# Check if a value already exists
		if key in obj:
			existing = obj[key]
		else:
			existing = sys_def
			obj[key] = existing
		
		# Sanity-check existing value
		if existing is None:
			existing = 'No default available'
		
		# Ask the user for input
		if castbool:
			substr = (existing and 'Yes') or (not existing and 'No')
		else:
			substr = existing
		
		r = raw_input(msg % substr)
		
		# Clean the input and check if it is valid
		r = r.strip()
		if len(r) > 0:
			# Update the object
			if castbool:
				obj[key] = 'y' in r.lower()
			else:
				obj[key] = r
		
		# No need to return, since Python is pass-by-object-reference...
	
	
	# If there is an existing file, load it
	if os.path.exists(YAMLCONF):
		stream = file(YAMLCONF, 'r')
		data = yaml.load(stream)
	else:
		# Create the default configuration object
		data = {
			'user':{},
			'OAuth2':{},
			'ISP':{},
			'smtp':{},
			'ssmtp':{},
		}
	
	# Try to work out default sender values
	try:
		default_name = os.getlogin() # Only works on Windows if using Python 3.x
	except Exception, err:
		default_name = 'mail'
	
	default_addr = '%s@%s' % (default_name, socket.getfqdn())
	
	# Specify the sender address and name
	updateConfig(data['user'],'sender', 'Sender email address (%s): ', default_addr)
	updateConfig(data['user'],'sender-name','Sender name (%s): ', default_name)
	
	# TO DO: Sanity-check sender fields here
	
	# Reply-to address and name
	updateConfig(data['user'],'reply-to','Reply-to address (%s): ',data['user']['sender'])
	updateConfig(data['user'],'reply-to-name','Reply-to name (%s): ',data['user']['sender-name'])
	
	# Use OAuth2?
	if useOAuth:
		print
		r = raw_input("Do you wish to use OAuth2 with Gmail? Visit https://console.developers.google.com/apis/credentials to set up a client ID and client secret first. [Y/N] ")
		if "y" in r.lower():
			updateConfig(data['OAuth2'],'client_id','Client ID (%s): ')
			updateConfig(data['OAuth2'],'client_secret','Client secret (%s): ')
		else:
			data['OAuth2'] = {}
	
	# ISP Relay?
	print 
	r = raw_input("Enable fallback to ISP relay? [Y/N] ")
	if "y" in r.lower():
		updateConfig(data['ISP'],'relay','Enter ISP relay FQDN (%s): ')
	else:
		data['ISP'] = {}
	
	# smtplib
	if useSMTP:
		print
		r = raw_input("Enable fallback to smtplib? This is not recommended, as your username and password are stored in plaintext. [Y/N] ")
		if "y" in r.lower():
			updateConfig(data['smtp'],'server','SMTP server (%s): ')
			updateConfig(data['smtp'],'port','SMTP port (%s): ')
			updateConfig(data['smtp'],'starttls','Use STARTTLS? (%s) [Y/N]: ', True, True)
			updateConfig(data['smtp'],'username','Username (%s): ')
			updateConfig(data['smtp'],'password','Password - are you sure you want to do this? (%s): ')
		else:
			data['smtp'] = {}
	
	# Subprocess SSMTP
	print
	r = raw_input("Enable fallback to subprocess and ssmtp? [Y/N] ")
	if "y" in r.lower():
		ssmtp_path = distutils.spawn.find_executable('ssmtp')
		if ssmtp_path is None:
			print 'SSMTP binary not detected in path. Please enter manually.'
		updateConfig(data['ssmtp'],'path','Enter the path to the SSMTP binary (%s): ',ssmtp_path)
	else:
		data['ssmtp'] = {}
	
	# Create the YAML config file
	stream = file(YAMLCONF, 'w')
	yaml.dump(data, stream)
	
	print
	print "Configuration complete."
	
	
def loadConfig():
	"""Load the YAML configuration file."""
	
	global conf
	
	# Ensure the file exists
	if os.path.exists(YAMLCONF):
		stream = file(YAMLCONF, 'r')
		conf = yaml.load(stream)
		
	else:
		raise OSError(errno.ENOENT, "Configuration file not found. Run the script with -c to create the configuration file.")


# Only execute when the script is called directly
if __name__ == '__main__':
	initOptions() # Parse command-line parameters
	if opts.configure:
		configureScript()
	else:
		loadConfig()
		if opts.test:
			logPrint('Command-line request for test email.')
			sendEmail(conf['user']['sender'])
		elif opts.init_oauth:
			logPrint('Command-line request for OAuth initialisation.')
			initialiseOAuth()
		else:
			logPrint('Command-line request for email.')
			prepEmail()

# Always execute, especially when importing
else:
	loadConfig() # Load the configuration file
