from flask import Blueprint, current_app, render_template, request, send_from_directory

import ordinarium

from .db import get_db

bp = Blueprint('main', __name__)


@bp.route('/favicon.ico')
def favicon():
	if current_app.static_folder is None:
		return '', 404
	return send_from_directory(current_app.static_folder, 'images/favicon.ico', mimetype='image/vnd.microsoft.icon')

@bp.route('/')
def index():
	title = 'Welcome to Ordinarium'
	content = '''
Ordinarium is a liturgy planning workspace supporting the assembly, ordering, and management of liturgical orders of service. We currently support the eucharistic services from the <a href="https://anglicanchurch.net/" target="_blank">Anglican Church in North America</a> *Book of Common Prayer* (2019).

**Begin [planning a service](/plan).**
'''
	return render_template('page.html', title=title, content=content)

@bp.route('/plan')
def plan(rite='Renewed Ancient Text'):
	db = get_db()
	ordinaries = db.execute('select id, default_order, title, detailed_title, text from texts where type=? and filter_type=? and filter_content=? order by default_order', ('ordinarium', 'rite', rite)).fetchall()
	return render_template('plan.html', rite=rite, ordinaries=ordinaries)

@bp.route('/text')
def text():
	ids = request.args.get('ids', '').split(',') if request.args.get('ids') else []
	ids_json = '[' + ','.join(ids) + ']' if ids else None
	print(ids_json)
	
	title = '<!--<small>The Order for the Administration of</small>  \nThe Lord’s Supper  \n<small>*or*</small>  \nHoly Communion,  \n<small>Commonly Called</small>  \n-->The Holy Eucharist'
	rite = 'Renewed Ancient Text'
	season = 'Christmastide'

	db = get_db()
	ordinaries = db.execute('select title, text from texts join json_each(?) ids on texts.id=ids.value where texts.type=? and texts.filter_type=? and texts.filter_content=? order by ids.key;', (ids_json, 'ordinarium', 'rite', rite)).fetchall() if ids_json else []
	# Move propers selection to class
	acclamation = db.execute('select text from texts where type=? and filter_type=? and filter_content=? order by random() limit 1', ('acclamation', 'season', season)).fetchone()
	offertory_sentence = db.execute('select text from texts where type=? order by random() limit 1', ('offertory_sentence',)).fetchone()
	proper_preface = db.execute('select text from texts where type=? and filter_type=? and filter_content=? order by random() limit 1', ('proper_preface', 'season', season)).fetchone()
	propers = {
		'acclamation': acclamation['text'] if acclamation else '*Error: No acclamation found.*',
		'collect_of_the_day': 'Almighty God, you have poured upon us the new light of your incarnate Word: Grant that this light, kindled in our hearts, may shine forth in our lives; through Jesus Christ our Lord, who lives and reigns with you in the unity of the Holy Spirit, one God, now and for ever. **Amen.**',
		'lesson_1_reference': 'Isaiah (61:10–62:5)',
		'psalm_reference': 'Psalm (147:12-20)',
		'lesson_2_reference': 'Galations (3:23–4:7)',
		'gospel_reference': 'John (1:1–18)',
		'offertory_sentence': offertory_sentence['text'] if offertory_sentence else '*Error: No offertory sentence found.*',
		'proper_preface': proper_preface['text'] if proper_preface else '*Error: No proper preface found.*',
	}
	return render_template('text.html', title=title, rite=rite, ordinaries=ordinaries, **propers)

@bp.route('/<slug>')
def page(slug):
	db = get_db()
	page = db.execute('select title, text from texts where type=? and slug=? limit 1', ('page', slug)).fetchone()
	if page:
		return render_template('page.html', title=page['title'], content=page['text'])
	else:
		return render_template('page.html', title='Error', content='Page not found'), 404
