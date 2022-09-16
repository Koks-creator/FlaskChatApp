from datetime import datetime
from dataclasses import dataclass
from typing import List
from flask_sqlalchemy import SQLAlchemy
from ChatAppFlask.config import app, MESSAGE_FETCH_LIMIT
from flask_bcrypt import Bcrypt
from flask_login import UserMixin

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String)
    member_of = db.relationship('ChatRoomMembers', backref='memberof', lazy=True)

    def __repr__(self):
        return f"User('{self.id}', '{self.username}', '{self.email}')"


class ChatRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.String(30), unique=False, nullable=False)
    members = db.relationship('ChatRoomMembers', backref='members', lazy=True)

    def __repr__(self):
        return f"ChatRoom('{self.id}', '{self.name}', '{self.created_at}', '{self.created_by}')"


class ChatRoomMembers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_name = db.Column(db.String(30), unique=False, nullable=False)
    is_room_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    added_by = db.Column(db.String(30), unique=False, nullable=False)

    def __repr__(self):
        return f"ChatRoomMembers('{self.id}', '{self.chat_room_id}', '{self.user_id}', '{self.room_name}'," \
            f" '{self.is_room_admin}', '{self.created_at}', '{self.added_by}')"


@dataclass
class Messages(db.Model):
    id: int
    chat_room_id: int
    text: str
    sender: str
    created_at: datetime

    id = db.Column(db.Integer, primary_key=True)
    chat_room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'), nullable=False)
    text = db.Column(db.String(255), unique=False, nullable=False)
    sender = db.Column(db.String(30), unique=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"Message('{self.id}', '{self.chat_room_id}', '{self.text}', '{self.sender}', '{self.created_at}')"


def fetch_data(table: db.Model) -> list:
    return table.query.all()


def add_user(username: str, email: str, password: str) -> bool:
    try:
        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        user = User(username=username, email=email, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        return True
    except Exception as e:
        print(e)
        return False


def save_room(room_name: str, created_by: str) -> int:
    room = ChatRoom(name=room_name, created_by=created_by)
    db.session.add(room)
    fetch_data(ChatRoom)

    room_id = room.id
    success = add_room_member(room_id, room_name, created_by, created_by, is_room_admin=True)
    if success:
        db.session.commit()
        return room_id
    else:
        return 0


def add_room_member(room_id: int, room_name: str, username: str, added_by: str, is_room_admin=False) -> bool:
    user_to_add = User.query.filter_by(username=username).first()

    if user_to_add:
        room = ChatRoom.query.filter_by(id=room_id).first()

        members_ids = [user.id for user in room.members]
        if user_to_add.id not in members_ids:
            member = ChatRoomMembers(chat_room_id=room_id, user_id=user_to_add.id, room_name=room_name, is_room_admin=is_room_admin,
                                     added_by=added_by)
            db.session.add(member)
            db.session.commit()
            return True
        else:
            return False
    return False


def add_room_members(room_id: int, room_name: str, usernames: list, added_by: str) -> list:
    """

    :param room_id:
    :param room_name:
    :param usernames:
    :param added_by:
    :return: added members ids list
    """
    members_list = []
    room = ChatRoom.query.filter_by(id=room_id).first()

    members_ids = [member.user_id for member in room.members]

    for username in usernames:
        user_to_add = User.query.filter_by(username=username).first()
        if user_to_add:
            if user_to_add.id not in members_ids:
                member = ChatRoomMembers(chat_room_id=room_id, user_id=user_to_add.id, room_name=room_name,
                                         is_room_admin=False,
                                         added_by=added_by)

                members_list.append(member)

    if len(members_list):
        db.session.add_all(members_list)
        db.session.commit()

        return members_list
    return []


def get_room(room_id: int) -> ChatRoom:
    room = ChatRoom.query.get(room_id)

    return room


def get_room_members(room_id: int) -> list:
    room_members = ChatRoom.query.get(room_id).members

    return room_members


def get_rooms_for_user(username: str) -> List[ChatRoom]:
    user = User.query.filter_by(username=username).first()

    rooms = [ChatRoom.query.get(member_obj.chat_room_id) for member_obj in user.member_of]

    return rooms


def is_room_member(room_id: int, username: str) -> bool:
    user = User.query.filter_by(username=username).first()
    if user:
        room_members = ChatRoom.query.get(room_id).members
        room_members_ids = [member.user_id for member in room_members]

        if user.id in room_members_ids:
            return True
        else:
            return False
    return False


def is_room_admin(room_id: int, username: str):
    chat_room = ChatRoom.query.get(room_id)
    if chat_room:
        if chat_room.created_by == username:
            return True
        return False
    return False


def update_room(room_id: int, new_room_name: str) -> bool:
    room = ChatRoom.query.get(room_id)

    if room:
        room.name = new_room_name
        db.session.commit()
        return True
    return False


def remove_room_members(room_id: int, usernames: list):
    room = ChatRoom.query.get(room_id)

    if room:
        for username in usernames:
            user = User.query.filter_by(username=username).first()
            if user and is_room_admin(room_id, username) is False:
                member = ChatRoomMembers.query.filter_by(user_id=user.id, chat_room_id=room_id).first()
                if member:
                    db.session.delete(member)
                    db.session.commit()
        return True
    return False


def save_message(room_id: int, text: str, sender: str) -> bool:
    try:
        message = Messages(chat_room_id=room_id, text=text, sender=sender)
        db.session.add(message)
        db.session.commit()
        return True
    except Exception as e:
        print(e)
        return False


def fetch_messages(room_id: int, page=0) -> List[dict]:
    offset = page * MESSAGE_FETCH_LIMIT
    messages = Messages.query.filter_by(chat_room_id=room_id).order_by(Messages.created_at.desc()).limit(MESSAGE_FETCH_LIMIT).offset(offset)

    cleaned_messages = []
    for msg in messages:
        cleaned_messages.append({"chat_room_id": msg.chat_room_id, "created_at": msg.created_at.strftime('%d %b %Y, %H:%M'),
                                 "id": msg.id, "sender": msg.sender, "text": msg.text})

    return cleaned_messages[::-1]


def delete_room(room_id: int) -> bool:
    room = get_room(room_id)
    if room:
        Messages.query.filter(Messages.chat_room_id== room_id).delete()
        ChatRoomMembers.query.filter(ChatRoomMembers.chat_room_id == room_id).delete()
        db.session.delete(room)

        db.session.commit()

        return True
    return False


if __name__ == '__main__':
    pass
    # db.create_all()
    # ChatRoomMembers.query.delete()
    # db.session.commit()
    # success = add_user("Admin", "admin@gmail.com", "admin")
    # success = add_user("Xd3", "xd3@gmail.com", "gigakoks123$x")
    # success = add_user("Xd2", "xd2@gmail.com", "gigakoks123$x")
    # print(fetch_data(Messages))
    #
    # room_id = save_room(room_name="TestRoom3", created_by="Admin")
    # print(room_id)
    # print(ChatRoom.query.get(room_id).members)
    #
    # # print(add_room_member(1, "TestRoom", "Admin", "Admin"))
    #
    # added = add_room_members(room_id, 'TestRoom2', ["Xd2", "Admin", "Xd3"], added_by="Admin")
    # print(added)

    # print(len(ChatRoom.query.get(2).members))

    # print(fetch_data(ChatRoom))
    # success = add_user("Xd2", "xd2@gmail.com", "gigakoks123$x")
    # print(success)

    # print(user.member_of)
    # save_room("ff2", "ff2")
    # for i in ChatRoom.query.get(1).members:
    #     print(User.query.get(i.id))
    # added = add_room_members(1, 'TestRoom', ["Admin"], added_by="Admin")
    # print(added)
    # print(get_room(1))
    # print(update_room(1, "NowyRoomName"))
    # print(get_room(1).members)
    # remove_room_members(2, ["Xd2", "Xd3", "dfdf"])
    # print(get_room(2).members)
    # print(get_rooms_for_user("Admin"))
    # for message in fetch_messages(1, page=0):
    #     print(message.created_at)
    # print(fetch_messages(1))
    # delete_room(2)
    # print(fetch_messages(1))