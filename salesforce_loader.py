#!/usr/bin/env python2

# Quality imports                                                             
# ////////////////////////////////////////////////////////////////////////////
import pickle
import os, re, sys
from markdown import markdown
from smartypants import smartypants as typography
from simple_salesforce import Salesforce
from config import (
    CACHE_FILE,
    IMAGE_DIRECTORY,
    OUTPUT_PREFIX,
    SALESFORCE_USERNAME,
    SALESFORCE_PASSWORD,
    SALESFORCE_SECURITY_TOKEN,
)

# Setup                                                                   
# ////////////////////////////////////////////////////////////////////////////
# Allow invocation of the script from anywhere
REAL_PATH = os.path.dirname(os.path.realpath(__file__))
os.chdir(REAL_PATH)

# Utilities                                                                   
# ////////////////////////////////////////////////////////////////////////////
warn = lambda s: sys.stderr.write(s + '\n') and sys.stderr.flush() 
die = lambda s: warn(s) or sys.exit(1)

# Mapping of field names between salesforce and jekyll front matter
# ////////////////////////////////////////////////////////////////////////////
fields = '''
    contributors        Primary_contributor_name__c
    id                  Id
    image_caption       image_caption__c
    image_link          IMAGE_LINK__c
    image_name          image_name__c
    image_source        image_source__c
    image_source_url    image_source_url__c
    learn_more          Learn_More__c
    related_solutions   Related_Solutions__c
    related_stories     Related_Stories__c
    related_theories    Related_Theories__c
    scale               Scale__c
    short_write_up      Short_Write_Up__c
    tags                Tags__c
    title               Name
    type                Type__c
    values              Values_exemplified__c
    when                When__c
    where               Where_del__c
    who                 Who__c
'''
jekyll2salesforce = dict(L.split() for L in fields.strip().splitlines())
salesforce2jekyll = {v:k for k,v in jekyll2salesforce.items()}

# Fetch records
# ////////////////////////////////////////////////////////////////////////////
# If the word "offline" is specified on the command line, use a cached query
if 'offline' in sys.argv:
    try:
        with open(CACHE_FILE, 'rb') as file:
            records = pickle.load(file)
    except IOError: 
        die("Can't work offline because no CACHE_FILE exists")
else:
    sf = Salesforce(
        username=SALESFORCE_USERNAME, 
        password=SALESFORCE_PASSWORD, 
        security_token=SALESFORCE_SECURITY_TOKEN
    )
    records = sf.query_all('''
        SELECT {} 
        FROM Beautiful_Solution__c
        WHERE on_website__c = true
    '''.format(','.join(salesforce2jekyll)))['records']
    with open(CACHE_FILE, 'wb') as file:
        pickle.dump(records, file)

# Clean and process records
# ////////////////////////////////////////////////////////////////////////////
# Convert record keys from salesforce to jekyll names, replace None w/'' & eliminate CRLFs
records = [{j: (r[s] or '').replace('\r\n','\n') for j,s in jekyll2salesforce.items()} for r in records]

for record in records:
    # Create a slug before modifying title
    record['slug'] = re.sub(r'(?u)\W', '-', record['title'].lower())

    # Typography filter
    for field in '''
        contributors 
        image_caption 
        image_source 
        short_write_up
        title 
    '''.split():
        record[field] = typography(record[field])

    # Markdown filter
    for field in '''
        short_write_up
    '''.split():
        record[field] = markdown(record[field])

    # Semicolon-delimited --> YAML lists filter
    for field in '''
        contributors 
        related_solutions 
        related_stories 
        related_theories 
        tags 
        values
    '''.split():
        value = record[field]
        if value.strip():
            record[field] = '\n' + '\n'.join(u'- "{}"'.format(i) for i in value.split(';'))
            
    # Learn more filter
    items = record['learn_more'].strip().split('\n\n')
    if all(items):
        learn_more = ''
        for item in items:
            try:
                title, desc, type, url = item.split('\n')
            # Ignore learn more items with bad formatting
            except ValueError: continue 
            learn_more += (
                u'\n-\n'
                '    title: "{}"\n'
                '    description: "{}"\n'
                '    type: "{}"\n'
                '    url: "{}"'
            ).format(typography(title), typography(desc), type, url)
        record['learn_more'] = learn_more

    # Scale is given as a list but not used that way
    record['scale'] = record['scale'].replace(';', ', ')

# Write the jekyll files
# ////////////////////////////////////////////////////////////////////////////
template = u'''---
id: {id}
title: "{title}"
short_write_up: "{short_write_up}"
where: "{where}"
when: "{when}"
who: "{who}"
scale: "{scale}"
values:{values}
related_solutions:{related_solutions}
related_theories:{related_theories}
related_stories:{related_stories}
tags:{tags}
learn_more:{learn_more}
images:
-
    url: "{image_name}"
    name: "{image_name}"
    caption: "{image_caption}"
    source: "{image_source}"
    source_url: "{image_source_url}"
contributors:{contributors}
---
'''
for record in records:
    output = template.format(**record).encode('utf8')

    # Create output directory
    directory = REAL_PATH + '/' + OUTPUT_PREFIX + {
        'Story':    '_stories',
        'Theory':   '_theories',
        'Value':    '_values',
        'Solution': '_solutions',
    }[record['type']]
    if not os.path.isdir(directory):
        os.mkdir(directory)
        warn('Created ' + directory)
    
    # Build path using the slug created above
    filename = u'{}/{}.md'.format(directory, record['slug'])

    # Produce tangible output! (But why not straight to json?)
    with open(filename, 'wb') as file:
        file.write(output)
        warn('Wrote ' + filename)

