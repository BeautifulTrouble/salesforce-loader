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
def warn(s, color=32):
    sys.stderr.write(u'\033[{}m{}\033[0m\n'.format(color, s))
    sys.stderr.flush()

def die(s):
    warn(s, color=31)
    sys.exit(1)

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
# Convert record keys from salesforce to jekyll names, replace None w/'' & remove carriage returns
records = [{j: (r[s] or '').replace('\r\n','\n') for j,s in jekyll2salesforce.items()} for r in records]

# Salesforce currently limits multi-select picklist fields to 40 characters.
# I need full titles to complete 2-way relationships between modules, so this
# mapping is for expanding truncated titles to their full names.
TITLE_LIMIT = 40
full_titles = {record['title'][:TITLE_LIMIT]: record['title'] for record in records}

# Map record types the related fields they belong in
relation_types = {
    'Solution': 'related_solutions',
    'Story':    'related_stories',
    'Theory':   'related_theories',
    'Value':    'values'
}

# Mapping to be filled with the implicit relationships (grumble grumble...)
# This should be handled by the Salesforce database!!! TODO: ask Eli
relationships = {record['title']: {t: set() for t in relation_types.values()} for record in records}

# Figure out all the implicit relationships
for record in records:
    this_title = record['title']
    this_type = relation_types[record['type']]
    for that_type in relation_types.values():
        for that_title in record[that_type].split(';'):
            if that_title in full_titles:
                that_title = full_titles[that_title]
                relationships[that_title][this_type].add(this_title)

# Insert them back into the the semicolon-delimited lists
for record in records:
    for that_type in relation_types.values():
        relations = relationships[record['title']]
        for that_title in record[that_type].split(';'):
            if that_title in full_titles:
                relations[that_type].add(full_titles[that_title])
        record[that_type] = ';'.join(relations[that_type])

# Spiff up the rest of the stuff
for record in records:
    # Create a slug before modifying title
    record['slug'] = re.sub(r'(?u)\W', '-', record['title'].lower())

    # Scale is given as a list but not used that way
    record['scale'] = record['scale'].replace(';', ', ')

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
            record[field] = '\n' + '\n'.join(u'- "{}"'.format(i) for i in sorted(value.split(';')))
            
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
    for k,v in record.items():
        record[k] = v.replace('"', '\\"')
    output = template.format(**record).encode('utf8')

    # Create output directory
    directory = os.path.join(REAL_PATH, OUTPUT_PREFIX, {
        'Story':    '_stories',
        'Theory':   '_theories',
        'Value':    '_values',
        'Solution': '_solutions',
    }[record['type']])
    if not os.path.isdir(directory):
        os.mkdir(directory)
        warn('Created ' + directory, color=33)
    
    # Build path using the slug created above
    filename = u'{}/{}.md'.format(directory, record['slug'])

    # Produce tangible output! (But why not straight to json?)
    with open(filename, 'wb') as file:
        file.write(output)
        warn('Wrote ' + filename)

