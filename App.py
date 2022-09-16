from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, request, flash, jsonify
from flask_socketio import SocketIO, join_room, leave_room
from flask_login import login_user, current_user, logout_user, login_required
from ChatAppFlask.config import socketio, app, login_manager
from ChatAppFlask.db import db, User, add_user, bcrypt
from json import dumps
import ChatAppFlask.db as db_functions


@login_manager.user_loader  # it checks before every request which user id is currently in the session
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def home():
    page = request.args.get('page', 1, type=int)  # Mozemy dzieki temu wpisywac numer strony - domyslnie jest 1
    rooms = []
    if current_user.is_authenticated:
        rooms = db_functions.get_rooms_for_user(current_user.username)
    return render_template("index.html", rooms=rooms)


@app.route('/login', methods=['POST', 'GET'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember_me = request.form.get('rememberme')

        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user, remember=remember_me)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash("Failed to login. Check your username and password", "danger")

    return render_template('login.html')


@app.route('/register', methods=['POST', 'GET'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('confirm_password')

        if password == password_confirm:
            add_user(username=username, email=email, password=password)
            flash("Account created!", "success")
            return redirect(url_for('login'))
        else:
            flash("Passwords must match each other!", "danger")

    return render_template('register.html')


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


@app.route('/create_room', methods=['GET', 'POST'])
@login_required
def create_room():
    if request.method == 'POST':
        room_name = request.form.get('room_name')
        usernames = [username.strip() for username in request.form.get('members').split(",")]

        if usernames and room_name:
            room_id = db_functions.save_room(room_name, current_user.username)
            # print(room_id)
            if room_id:
                if current_user.username in usernames:
                    usernames.remove(current_user.username)

                db_functions.add_room_members(room_id, room_name, usernames, current_user.username)
                flash("Room created!", "success")
                return redirect(url_for("view_room", room_id=room_id))
            else:
                flash("Failed to create a room", "danger")

    return render_template('create_room.html')


@app.route('/rooms/<room_id>')
@login_required
def view_room(room_id):
    room = db_functions.get_room(room_id)
    if room and db_functions.is_room_member(room_id, current_user.username):
        room_members_raw = db_functions.get_room_members(room_id)
        room_members = [User.query.get(member.user_id).username for member in room_members_raw]
        messages = db_functions.fetch_messages(room_id)

        room_admin = db_functions.is_room_admin(room_id, current_user.username)
        return render_template('view_room.html', username=current_user.username, room=room, room_members=room_members,
                               messages=messages, room_admin=room_admin)
    else:
        return "Room not found", 404


@app.route('/rooms/<room_id>/messages/')
@login_required
def get_older_messages(room_id):
    room = db_functions.get_room(room_id)
    if room and db_functions.is_room_member(room_id, current_user.username):
        page = request.args.get('page', 0, int)
        messages_raw = db_functions.fetch_messages(room_id, page=page)

        return jsonify(messages_raw)
    else:
        return "Room not found", 404


@app.route('/rooms/<room_id>/edit', methods=['GET', 'POST'])
@login_required
def update_room(room_id):
    if db_functions.is_room_admin(room_id, current_user.username):
        room = db_functions.get_room(room_id)

        existing_room_members = []
        for member in room.members:
            user = User.query.get(member.user_id)
            existing_room_members.append(user.username)
        room_members_str = ",".join(existing_room_members)

        if request.method == 'POST':
            new_name = request.form.get('room_name')
            new_members = [member.strip() for member in request.form.get('members').split(",")]
            update_room_success = db_functions.update_room(room_id, new_name)

            if update_room_success:
                flash("Name changed successfully!", "success")
            else:
                flash("Failed to update room's name", "danger")

            members_to_add = list(set(new_members) - set(existing_room_members))
            members_to_remove = list(set(existing_room_members) - set(new_members))

            try:
                members_to_add.remove("")
                members_to_remove.remove("")
            except ValueError:
                pass

            if len(members_to_add):
                added_members_ids = db_functions.add_room_members(room_id, room.name, members_to_add, current_user.username)
                if added_members_ids:
                    added_members = [User.query.get(member.user_id).username for member in added_members_ids]
                    added_members = list(set(added_members + new_members))
                    room_members_str = ",".join(added_members)
                flash("Members added successfully!", "success")

            if len(members_to_remove):
                db_functions.remove_room_members(room_id, members_to_remove)
                room_members_str = ",".join(new_members)
                flash("Members removed successfully!", "success")

        return render_template("edit_room.html", room=room, room_members_str=room_members_str)
    else:
        return "Room not found", 404


@app.route('/rooms/<room_id>/delete', methods=['POST'])
@login_required
def delete_room(room_id):
    if db_functions.is_room_admin(room_id, current_user.username):
        success = db_functions.delete_room(room_id)
        if success:
            flash("Room deleted", "success")
            return redirect(url_for('home'))
        else:
            flash("Failed to delete room", "danger")
            return redirect(url_for('view_room', room_id=room_id))


@socketio.on('send_message')
def handle_send_message_event(data):
    app.logger.info("{} has sent message to the room {}: {}".format(data['username'],
                                                                    data['room'],
                                                                    data['message']))
    data['created_at'] = datetime.now().strftime('%d %b %Y, %H:%M')
    db_functions.save_message(data['room'], data['message'], data['username'])
    socketio.emit('receive_message', data, room=data['room'])


@socketio.on('join_room')
def handle_join_room_event(data):
    app.logger.info("{} has joined the room {}".format(data['username'], data['room']))
    join_room(data['room'])
    socketio.emit('join_room_announcement', data, room=data['room'])


@socketio.on('leave_room')
def handle_leave_room_event(data):
    app.logger.info("{} has left the room {}".format(data['username'], data['room']))
    leave_room(data['room'])
    socketio.emit('leave_room_announcement', data, room=data['room'])


if __name__ == '__main__':
    db.create_all()
    socketio.run(app, debug=True)
