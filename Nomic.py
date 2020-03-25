import discord
from discord.ext import commands
from discord.utils import get
import random as rnd
import openpyxl
import asyncio
import datetime as dt

#token.txt is a file not uploaded to git, containing the bot token and server name
with open("token.txt", 'r') as f:
    token = f.readline()[:-1]
    botID = f.readline()[:-1]
    serverName = f.readline()

client = discord.Client()
bot = commands.Bot(command_prefix='~', case_insensitive = True)
bot.remove_command('help')

'''
player.currentVote
0 : Non-vote
1 : Yes
2 : No
-1 : Forfeit
-2 : Non-player

Turn is the index of the current players turn, or the next player in the case where the game is between turns
It skips players who have left the game, and loops back to 0
globalTurn is the actual turn of the game. It only increments by 1

state
0 : The previous turn has ended, and the bot is waiting for historians to formalise the end of the turn and start the next
1 : The current player is writing a proposal to to be discussed and voted on
2 : A proposal has been made and player can vote for it


turn.end
0 : All votes
1 : Sufficient votes
2 : Out of proposal time
3 : Out of voting time
'''


players = []
class Player(object):
    def __init__(self, discObj, globalTurn):
        self.discord = discObj
        self.points = 0
        self.stillPlaying = True
        if game.state != 2:
            self.currentVote = None
        else:
            self.currentVote = -2
        self.voteHistory = [-2] * globalTurn
        self.online = True
        statNames = ['messages','daysPlaying','daysOnline','proposals','firstVotes','lastVotes']
        self.stats = {i : 0 for i in statNames}
    def __repr__(self):
        try:
            return self.discord.display_name
        except:
            return self.discord


turns = []
class Turn(object):
    def __init__(self, turn):
        self.turnNumber = turn
        self.proponent = None
        self.passed = None
        self.end = None
    def __repr__(self):
        try:
            return str(self.turnNumber) + ': ' + str(self.proponent.display_name)
        except:
            return str(self.turnNumber) + ': ' + str(self.proponent)


game = None
class Parameters(object):
    def __init__(self):
        self.turn = None
        self.globalTurn = None
        self.state = None
        self.proposalTime = None
        self.votingTime = None
        self.yesProportion = None
        self.firstVote = None
        self.lastVote = None
    def __repr__(self):
        return 'Turn:' + str(self.globalTurn) + '  State:' + str(self.state)



#Excel sheets
wb = openpyxl.load_workbook('Nomic.xlsx')
ws1 = wb['Players']
ws2 = wb['Turns']
ws3 = wb['Misc']

def loadData():
    global game, players, turns
    if game is not None:
        return
    game = Parameters()
    game.turn = ws3['B3'].value
    game.globalTurn = ws3['B4'].value
    game.state = ws3['B5'].value
    game.firstVote = ws3['B7'].value
    game.lastVote = get(players, discord__id = ws3['B8'].value)
    game.proposalTime = ws3['B10'].value
    game.votingTime = ws3['B11'].value
    game.yesProportion = ws3['B12'].value

    for i in range(ws3['B1'].value):
        nextPlayer = get(nomicServer.members, id=int(ws1.cell(3, i+2).value))
        nextPlayer = Player(nextPlayer, game.globalTurn)
        if nextPlayer.discord is None:
            nextPlayer.discord = ws1.cell(1, i+2).value
        nextPlayer.stillPlaying = ws1.cell(5, i+2).value
        nextPlayer.stillPlaying = ws1.cell(6, i+2).value
        nextPlayer.currentVote = ws1.cell(7, i+2).value
        nextPlayer.online = ws1.cell(8, i+2).value
        for j in range(game.globalTurn):
            nextPlayer.voteHistory[j] = ws2.cell(j+3, i+6).value
            nextPlayer.points[j] = ws3.cell(j+3,i+9).value
        j = 11
        for k in nextPlayer.stats:
            nextPlayer.stats[k] = ws1.cell(j, i+2).value
            j += 1
        players.append(nextPlayer)

    for i in range(game.globalTurn):
        nextTurn = Turn(i)
        nextTurn.proponent = get(nomicServer.members, id=int(ws2.cell(i+3, 2).value))
        if nextTurn.proponent is None:
            nextTurn.proponent = ws2.cell(i+3, 3).value
        nextTurn.passed = ws2.cell(i+3, 4).value
        nextTurn.end = ws2.cell(i+3, 5).value
        turns.append(nextTurn)


setup = False
@bot.event
async def on_ready():
    if setup:
        return
    setup = True
    global nomicServer, botMember, botChannel, updateChannel, votingChannel, playerRole
    #Commonly used channels and roles
    nomicServer = get(bot.guilds, name='Nomic')
    botMember = get(nomicServer.members, id=int(botID))

    botChannel = get(nomicServer.channels, name='bot-commands')
    updateChannel = get(nomicServer.channels, name='game-updates')
    votingChannel = get(nomicServer.channels, name='voting')

    playerRole = get(nomicServer.roles, name='Player')

    loadData()

    #Initial state role
    await bot.change_presence(activity=discord.Game(name='~help'))
    for role in nomicServer.roles:
        if role.name.startswith('Game State:'):
            await role.delete()
    roleNames = ['Game State: Waiting', 'Game State: Proposing', 'Game State: Voting']
    newRole = await nomicServer.create_role(name=roleNames[game.state], colour=discord.Colour(0x992d22), hoist=True)
    await botMember.add_roles(newRole)

    print("Bot is ready")


helpText = """```
~help
Displays this message

~join
Gives a non-player the player role and adds them into the turn order in a random position
Called by non-players in #bot-commands at any time

~ready
Causes the game to move from a state of waiting to the start of the next turn
Called by historians in #bot-commands during the waiting phase

~propose
Begins the voting process once the current player has made a proposal
Called by the current player in #voting during the proposal phase

~yes/no
Votes for or against the current proposal
Called by players in #voting during the voting phase

~save
Saves the data the bot has, to be used before the bot shuts down
```"""

@bot.command()
async def help(ctx):
    await ctx.author.send(helpText)

@bot.command()
async def save(ctx):
    await saveData()


@bot.command()
async def join(ctx):
    global players
    if ctx.channel != botChannel:
        return
    player = get(players, discord=ctx.author)
    if player is not None:
        #When the author is/was part of the game
        index = players.index(get(players, discord=ctx.author))
        if player.stillPlaying:
            await botChannel.send("You are already a player")
        else:
            player.stillPlaying = True
            await botChannel.send("{} has rejoined the game!".format(player.discord.mention))
            #Find the players before and after in the turn order who are still playing
            i = index
            while not players[i-1].stillPlaying:
                i -= 1
                if i == -1:
                    i = len(players) -1
            before = players[i-1].discord.display_name
            i = index
            while not players[i+1].stillPlaying:
                i += 1
                if i == len(players)-1:
                    i = -1
            after = players[i+1].discord.display_name
            await ctx.author.add_roles(playerRole)
            await botChannel.send("You are player #{} in the turn order, between {} & {}".format(index+1, before, after))
        return
    #New Player
    await botChannel.send("{} has joined the game!".format(ctx.author.mention))
    await ctx.author.add_roles(playerRole)
    newPlayerObj = Player(ctx.author, game.globalTurn)
    if len(players) == 0:
        newPlayer(0, newPlayerObj)
        await saveData()
        return
    #Pick a random place to insert the player into
    placement = rnd.randint(0,len(players)-1)
    if placement == 0 and rnd.randint(0,1) == 0:
        #The first and last position are equivalent, so there is a 50% chance of each
        placement = len(players)
    newPlayer(placement, newPlayerObj)
    #Find the players before and after who are still part of the game
    i = placement
    while not players[i-1].stillPlaying:
        i -= 1
        if i == -1:
            i = len(players) -1
    before = players[i-1].discord.display_name
    i = placement
    if i == len(players)-1:
        i = -1
    while not players[i+1].stillPlaying:
        i += 1
        if i == len(players)-1:
            i = -1
    after = players[i+1].discord.display_name
    if len(players) > 2:
        await botChannel.send("You are player #{} in the turn order, between {} & {}".format(placement+1, before, after))
    await saveData()

def newPlayer(index, player):
    global players, game
    #If the new player is before the current player, increment turn unless the game hasn't started yet
    if index <= game.turn and not (game.globalTurn == 0 and game.state == 0):
        game.turn += 1
    if index == len(players):
        players = players + [player]
    else:
        players = players[:index] + [player] + players[index:]


@bot.command()
async def ready(ctx):
    global game
    if not (ctx.channel == botChannel and game.state == 0 and get(nomicServer.roles,name='Historian') in ctx.author.roles):
        return
    #Begin the proposal phase
    game.state = 1
    #Give roles
    await updateChannel.send("{}'s turn has begun, make a proposal using ~propose".format(players[game.turn].discord.mention))
    currentPlayerRole = get(nomicServer.roles, name='Current Player')
    await players[game.turn].discord.add_roles(currentPlayerRole)
    newRole = await nomicServer.create_role(name='Game State: Proposing', colour=discord.Colour(0x992d22), hoist=True)
    await botMember.add_roles(newRole)
    oldRole = get(nomicServer.roles, name='Game State: Waiting')
    await oldRole.delete()
    #Begin timer for proposing
    global proposalTask
    proposalTask = asyncio.create_task(proposalTimeLimit())

async def proposalTimeLimit():
    await asyncio.sleep(game.proposalTime -3600)
    await votingChannel.send("{}, you have one hour left to propose".format(players[game.turn].discord.mention))
    await asyncio.sleep(3600)
    await updateChannel.send("A proposal was not made in time, waiting for the next turn")
    await endTurn(0, 3)


@bot.command()
async def propose(ctx):
    global players, game
    if not (ctx.channel == votingChannel and game.state == 1 and ctx.author == players[game.turn].discord):
        return
    #FirstVote is whether or not the first vote has been made yet, lastVote is the index of the most recent vote
    game.firstVote = False
    game.lastVote = None
    toVoteRole = get(nomicServer.roles, name='To Vote')
    for player in players:
        if player.stillPlaying:
            player.currentVote = 0
            await player.discord.add_roles(toVoteRole)
        else:
            player.currentVote = -2
    players[game.turn].stats['proposals'] += 1
    #End timer
    global proposalTask
    proposalTask.cancel()
    #Begin voting phase
    game.state = 2
    text = "'s proposal is available to vote on!\nVote with ~yes or ~no"
    await votingChannel.send("{} {}{}".format(playerRole.mention, ctx.author.display_name, text))
    #Give roles
    newRole = await nomicServer.create_role(name='Game State: Voting', colour=discord.Colour(0x992d22), hoist=True)
    await botMember.add_roles(newRole)
    oldRole = get(nomicServer.roles, name='Game State: Proposing')
    await oldRole.delete()
    #Begin voting timer
    global voteTask
    voteTask = asyncio.create_task(votingTimeLimit())

async def votingTimeLimit():
    global game
    await asyncio.sleep(game.votingTime -3600)
    toVoteRole = get(nomicServer.roles, name='To Vote')
    await votingChannel.send("{}, you have one hour left to vote".format(toVoteRole.mention))
    await asyncio.sleep(3600)
    await votingChannel.send("Voting time is up")
    game.lastVote = None
    await checkVotes(1)


@bot.command()
async def yes(ctx):
    global players, game
    if not (ctx.channel == votingChannel and game.state == 2 and ctx.author in [x.discord for x in players]):
        return
    player = get(players, discord = ctx.author)
    if player.currentVote == 0:
        player.currentVote = 1
        await votingChannel.send("{} has voted!".format(ctx.author.display_name))
        toVoteRole = get(nomicServer.roles, name='To Vote')
        await ctx.author.remove_roles(toVoteRole)
    elif player.currentVote != -2:
        await votingChannel.send("You've already voted")
    if players.index(player) != game.turn:
        if not game.firstVote:
            game.firstVote = True
            player.stats['firstVotes'] += 1
        game.lastVote = player
    await checkVotes(0)

@bot.command()
async def no(ctx):
    global players, game
    if not (ctx.channel == votingChannel and game.state == 2 and ctx.author in [x.discord for x in players]):
        return
    player = get(players, discord=ctx.author)
    if player.currentVote == 0:
        player.currentVote = 2
        await votingChannel.send("{} has voted!".format(ctx.author.display_name))
        toVoteRole = get(nomicServer.roles, name='To Vote')
        await ctx.author.remove_roles(toVoteRole)
    elif player.currentVote != -2:
        await votingChannel.send("You've already voted")
    if players.index(player) != game.turn:
        if not game.firstVote:
            game.firstVote = True
            player.stats['firstVotes'] += 1
        game.lastVote = player
    await checkVotes(0)

async def checkVotes(timeUp):
    global game
    allVotes = True
    yesses = 0
    nos = 0
    for player in players:
        if player.currentVote == 0 and player.stillPlaying:
            allVotes = False
        elif player.currentVote == 1: yesses += 1
        elif player.currentVote == 2: nos += 1
    #All votes have been cast
    if allVotes:
        if yesses/(yesses+nos) >= game.yesProportion - 0.001:
            await updateChannel.send("All votes have been cast and the proposal has passed. Waiting for the next turn to start")
            await endTurn(1, 0)
        else:
            await updateChannel.send("All votes have been cast and the proposal has failed. Waiting for the next turn to start")
            await endTurn(0, 0)
        return
    #Time is up
    if timeUp:
        if yesses + nos == 0:
            await updateChannel.send("The proposal has failed as no votes were cast, waiting for the next turn to start")
            await endTurn(0, 2)
        elif yesses/(yesses+nos) >= game.yesProportion - 0.001:
            await updateChannel.send("Voting time is up, and the proposal has passed. Waiting for the next turn to start")
            await endTurn(1, 2)
        else:
            await updateChannel.send("Voting time is up, and the proposal has failed. Waiting for the next turn to start")
            await endTurn(0, 2)
        return
    #Enough votes to determine a conclusion
    if yesses/sum([x.stillPlaying for x in players]) >= game.yesProportion - 0.001:
        await updateChannel.send("There are enough yes votes for the proposal to pass. Waiting for the next turn to start")
        await endTurn(1, 1)
    if nos/sum([x.stillPlaying for x in players]) > (1-game.yesProportion) + 0.001:
        await updateChannel.send("There are enough no votes for the proposal to fail. Waiting for the next turn to start")
        await endTurn(0, 1)


async def endTurn(success, endCondition):
    global players, game
    #Points
    if success:
        pointAdd = 0
        for player in players:
            if player.currentVote == 1:
                pointAdd += 2
            elif player.currentVote == 2:
                player.points += 5
        players[turn].points += pointAdd
        await updateChannel.send('Point changes:')
        await updateChannel.send('+' + pointAdd + ': ' + players[turn].discord.display_name)
        ioptns = '+5: '
        for player in players:
            if player.currentVote == 2:
                ioptns += player.discord.display_name + ' '
        if len(ioptns) >= 5:
            await updateChannel.send(ioptns)

    elif endCondition != 3:
        players[turn].points -= 10
        await updateChannel.send('Point changes:')
        await updateChannel.send('-10: ' + players[turn].discord.display_name)
    #Remove roles
    currentPlayerRole = get(nomicServer.roles, name='Current Player')
    toVoteRole = get(nomicServer.roles, name='To Vote')
    await players[game.turn].discord.remove_roles(currentPlayerRole)
    for player in players:
        if player.stillPlaying:
            await player.discord.remove_roles(toVoteRole)
    for role in nomicServer.roles:
        if role.name.startswith('Game State:'):
            await role.delete()
    newRole = await nomicServer.create_role(name='Game State: Waiting', colour=discord.Colour(0x992d22), hoist=True)
    await botMember.add_roles(newRole)
    if game.lastVote is not None:
        players[game.lastVote].stats['lastVotes'] += 1
    #Begin waiting phase
    turn = Turn(game.globalTurn)
    turn.proponent = players[game.turn]
    turn.passed = success
    turn.end = endCondition
    for player in players:
        player.voteHistory.append(player.currentVote)
        player.currentVote = None
    game.state = 0
    game.turn += 1
    game.globalTurn += 1
    if game.turn >= len(players):
        game.turn = 0
    while not players[game.turn].stillPlaying:
        game.turn += 1
        if game.turn > len(players):
            game.turn = 0
    game.firstVote = False
    game.lastVote = None
    turns.append(turn)
    await saveData()


async def saveData():
    ws3['B1'] = len(players)
    ws3['B3'] = game.turn
    ws3['B4'] = game.globalTurn
    ws3['B5'] = game.state
    for player in players:
        i = players.index(player)
        if player.discord in nomicServer.members:
            ws1.cell(1, i+2, player.discord.display_name)
            ws2.cell(1, i+6, player.discord.display_name)
            ws1.cell(2, i+2, player.discord.name)
            ws1.cell(3, i+2, str(player.discord.id))
        ws1.cell(5, i+2, player.stillPlaying)
        ws1.cell(6, i+2, player.points)
        ws1.cell(7, i+2, player.currentVote)
        ws1.cell(8, i+2, player.online)
    ws3['B7'] = game.firstVote
    if game.lastVote is not None:
        ws3['B8'] = game.lastVote.discord.id
    else: ws3['B8'] = None

    for i in range(game.globalTurn):
        for player in players:
            ws2.cell(i+3, players.index(player)+6, player.voteHistory[i])
            ws3.cell(i+3, players.index(player)+9, player.points[i])
        ws2.cell(i+3, 1, turns[i].turnNumber)
        proponent = turns[i].proponent.discord
        if not isinstance(proponent, str):
            ws2.cell(i+3, 2, str(proponent.id))
            ws2.cell(i+3, 3, proponent.display_name)
        ws2.cell(i+3, 4, turns[i].passed)
        ws2.cell(i+3, 5, turns[i].end)
    for player in players:
        i = 11 
        for stat in player.stats.values():
            ws1.cell(i, players.index(player)+2, stat)
            i += 1

    wb.save('Nomic.xlsx')
    print("Saved")


'''
@bot.command()
async def tz(ctx, tz):
    if not ((tz[0] == '+' or tz[0] == '-') and int(tz[1:]) <= 13 and tz != '-0' and ctx.channel == generalChannel):
        return
    newRole = get(nomicServer.roles, name = 'Time Zone ' + tz)
    if newRole is None:
        newRole = await nomicServer.create_role(name = 'Time Zone ' + tz)
    for role in ctx.author.roles:
        if role.name.startswith('Time Zone '):
            #Remove role
            if role.name.endswith(tz):
                if len(role.members) == 1:
                    await role.delete()
                else:
                    await ctx.author.remove_roles(role)
            #Replace role
            else:
                if len(role.members) == 1:
                    await role.delete()
                else:
                    await ctx.author.remove_roles(role)
                await ctx.author.add_roles(newRole)
            return
    await ctx.author.add_roles(newRole)
'''


@bot.event
async def on_message(ctx):
    if ctx.author in [x.discord for x in players]:
        player = get(players, discord = ctx.author)
        player.stats['messages'] += 1
    await bot.process_commands(ctx)

async def daily():
    global players
    #Loops once per day
    while True:
        tomorrow = dt.date.today() + dt.timedelta(days=1)
        midnight = dt.datetime.combine(tomorrow, dt.time.min)
        #Loops once per 15 minutes
        while True:
            now = dt.datetime.now()
            difference = (midnight-now).total_seconds()
            for player in players:
                if player.stillPlaying and not player.online:
                    if player.discord.status == "online":
                        player.online = True
            if difference < 900:
                break
            await asyncio.sleep(900)
            await saveData()
        for player in players:
            if player.stillPlaying:
                player.stats['daysPlaying'] += 1
            if player.online:
                player.stats['daysOnline'] += 1
        await asyncio.sleep(difference + 60)
        await saveData()


players = []
bot.loop.create_task(daily())

bot.run(token)