from flask import Blueprint, render_template

import ordinarium

from .db import get_db

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
	title = '<small>The Order for the Administration of</small>  \nThe Lord’s Supper  \n<small>*or*</small>  \nHoly Communion,  \n<small>Commonly Called</small>  \nThe Holy Eucharist'
	rite = 'Renewed Ancient Text'
	season = 'Christmastide'

	db = get_db()
	ordinaries = db.execute('select title, text from texts where type=? and filter_type=? and filter_content=? order by default_order', ('ordinarium', 'rite', rite)).fetchall()
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
	return render_template('index.html', title=title, rite=rite, ordinaries=ordinaries, **propers)
