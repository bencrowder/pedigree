import os
import cgi
import re

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app


class Person(db.Model):
	pedigree = db.ReferenceProperty()
	head = db.StringProperty(multiline=True)
	tail = db.StringProperty(multiline=True)
	father = db.SelfReferenceProperty(collection_name='person_father_set')
	mother = db.SelfReferenceProperty(collection_name='person_mother_set')

class Pedigree(db.Model):
	slug = db.StringProperty()
	root = db.ReferenceProperty(Person, collection_name='pedigree_root_set')
	gens = db.IntegerProperty()
	notes = db.TextProperty()
	date_added = db.DateTimeProperty(auto_now_add=True)
	owner = db.StringProperty()



########## Helper functions

def add_cell(text, celltype, rowspan, boxtype=''):
	output = '\t<td'

	if rowspan > 1:
		output += ' rowspan="' + str(rowspan) + '"'

	output += ' class="' + celltype
	if boxtype == 'father' and celltype == 'tail':
		output += ' leftborder'
	if boxtype == 'mother' and celltype == 'head':
		output += ' leftborder'
	output += '">' + re.sub(r'\r', r'<br/>', text) + '</td>'

	if rowspan == 1:							# if rowspan is 1, need to end current row
		output += '\n</tr>'
		if boxtype != '':						# and start a new one unless we're done
			output += '\n<tr>'

	return output


def write_pedigree(person, cur_gen, n, boxtype):
	output = ''

	if not person:
		person = Person()

	if boxtype == '':
		output += '<table cellpadding="0" cellspacing="0" border="0">'
		output += '<tr>'

	if cur_gen == n:
		closerow = 1
	output += add_cell(person.head, 'head', 2 ** (n - cur_gen), boxtype)
	if cur_gen < n:
		output += write_pedigree(person.father, cur_gen + 1, n, 'father')
	output += add_cell(person.tail, 'tail', 2 ** (n - cur_gen), boxtype)
	if cur_gen < n:
		output += write_pedigree(person.mother, cur_gen + 1, n, 'mother')

	if boxtype == '':
		output += '</table>'

	return output

def save_tree(self, cur, base, n, pedigree, gens):
	if n <= gens:
		if not cur:
			cur = Person()
			cur.pedigree = pedigree.key()
		cur.head = self.request.get(base)
		cur.tail = self.request.get(base + '_tail')

		cur.father = save_tree(self, cur.father, base + '_father', n + 1, pedigree, gens)
		cur.mother = save_tree(self, cur.mother, base + '_mother', n + 1, pedigree, gens)
		cur.put()
		return cur.key()

def get_login_url(self):
	if users.get_current_user():
		url = users.create_logout_url(self.request.uri)
		url_linktext = 'Logout'
		logged_in = True
		list_url = '/' + users.get_current_user().nickname() + '/list'
	else:
		url = users.create_login_url(self.request.uri)
		url_linktext = 'Login'
		logged_in = False
		list_url = ''
	return (url, url_linktext, logged_in, list_url)

def get_header_values(self, pagetitle):
	url, url_linktext, logged_in, list_url = get_login_url(self)

	return {
		'title': pagetitle,
		'url': url,
		'url_linktext': url_linktext,
		'logged_in' : logged_in,
		'list_url' : list_url
	}

def render_page(self, pagename, header_values, page_values={}, footer_values={}):
	path = os.path.join(os.path.dirname(__file__), 'templates/header.html')
	self.response.out.write(template.render(path, header_values))

	path = os.path.join(os.path.dirname(__file__), 'templates/' + pagename + '.html')
	self.response.out.write(template.render(path, page_values))
	
	path = os.path.join(os.path.dirname(__file__), 'templates/footer.html')
	self.response.out.write(template.render(path, footer_values))


########## Web classes

class index(webapp.RequestHandler):
	def get(self):
		user = users.get_current_user()
		if user:
			header_values = get_header_values(self, 'Pedigree Chart')
			page_values = {
				'base_url' : 'http://pedigreechart.appspot.com/' + user.nickname() + '/'
			}
			render_page(self, 'index', header_values, page_values)
		else:
			self.redirect(users.create_login_url(self.request.uri))


class view(webapp.RequestHandler):
    def get(self, user, slug):
		pedigrees = Pedigree.gql("WHERE owner = :1 AND slug = :2 LIMIT 1", user, slug)
		for pedigree in pedigrees:
			html = write_pedigree(pedigree.root, 1, pedigree.gens, '')
			notes = pedigree.notes

		header_values = get_header_values(self, slug + ' | Pedigree Chart')
		page_values = { 'slug' : slug, 'html' : html, 'notes' : notes }
		render_page(self, 'view', header_values, page_values)


class add(webapp.RequestHandler):
	def post(self):
		pedigree = Pedigree()
	
		pedigree.slug = self.request.get('slug')
		pedigree.gens = 3
		pedigree.notes = self.request.get('notes')
		pedigree.owner = users.get_current_user().nickname()
		pedigree.put()

		root = Person()
		root.pedigree = pedigree.key()
		save_tree(self, root, 'root', 1, pedigree, pedigree.gens)

		pedigree.root = root.key()
		pedigree.put()
		self.redirect('/' + users.get_current_user().nickname() + '/view/' + pedigree.slug)


class list(webapp.RequestHandler):
    def get(self, user):
		pedigrees = Pedigree.gql("WHERE owner = :1", user)

		header_values = get_header_values(self, 'Pedigrees by ' + user)
		page_values = { 'username' : user, 'pedigrees' : pedigrees }
		render_page(self, 'list', header_values, page_values)


########## Main

application = webapp.WSGIApplication(
									[('/', index),
									(r'/add', add),
									(r'/(.*)/list', list),
									(r'/(.*)/view/(.*)', view)], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
