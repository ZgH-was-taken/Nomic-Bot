import discord
from discord.ext import commands
from discord.utils import get
import random as rnd
import openpyxl
import asyncio
import datetime as dt
import math

#token.txt is a file not uploaded to git, containing the bot token and server name
with open("token.txt", 'r') as f:
    token = f.readline()[:-1]
    botID = f.readline()

client = discord.Client()
bot = commands.Bot(command_prefix='~', case_insensitive = True)
bot.remove_command('help')

'''
player.currentVote [x,y]
x:
0 : Non-vote
1 : Yes
2 : No
-1 : Forfeit
-2 : Inactive player

y: Order of votes

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
2 : Out of voting time
3 : Out of proposal time
'''


players = []
class Player(object):
    def __init__(self, discObj, globalTurn):
        self.discord = discObj
        self.points = 0
        self.active = True
        self.lastMessage = None
        if game.state != 2:
            self.currentVote = [None,None]
        else:
            self.currentVote = [-2,None]
        self.voteHistory = [[-2,None]] * (globalTurn)
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
        self.yesProportion = [None,None]
        self.timeoutProportion = [None,None]
        self.timeoutMinimum = [None,None]
        self.timerEnd = None
        self.firstVote = None
        self.lastVote = None
    def __repr__(self):
        return 'Turn:' + str(self.globalTurn) + '  State:' + str(self.state)



#Excel sheets
wb = openpyxl.load_workbook('nomic.xlsx')
ws1 = wb['Players']
ws2 = wb['Turns']
ws3 = wb['Misc']
ws4 = wb['Rules']

def loadData():
    global game, players, turns, summaryMsgID
    if game is not None:
        return
    game = Parameters()
    game.turn = ws3['B3'].value
    game.globalTurn = ws3['B4'].value
    game.state = ws3['B5'].value
    game.firstVote = ws3['B7'].value
    try:
        game.lastVote = get(players, discord__id = int(ws3['B8'].value))
    except TypeError:
        game.lastVote = None
    game.voteNumber = ws3['B9'].value
    game.proposalTime = ws3['B11'].value
    game.votingTime = ws3['B12'].value
    game.yesProportion = [float(i) for i in ws3['B13'].value.split(',')]
    game.timeoutProportion = [float(i) for i in ws3['B14'].value.split(',')]
    game.timeoutMinimum = [float(i) for i in ws3['B15'].value.split(',')]
    game.transmute = ws3['B16'].value
    game.timerEnd = ws3['B17'].value
    summaryMsgID = ws3['B19'].value
    if summaryMsgID:
        summaryMsgID = int(summaryMsgID)

    for i in range(ws3['B1'].value):
        nextPlayer = get(nomicServer.members, id=int(ws1.cell(3, i+2).value))
        nextPlayer = Player(nextPlayer, game.globalTurn)
        if nextPlayer.discord is None:
            nextPlayer.discord = ws1.cell(1, i+2).value
        nextPlayer.active = ws1.cell(5, i+2).value
        nextPlayer.lastMessage = ws1.cell(6, i+2).value
        nextPlayer.points = ws1.cell(7, i+2).value
        if ws1.cell(8, i+2).value is None:
            nextPlayer.currentVote = [None,None]
        elif ws1.cell(8, i+2).value[-1] == ',':
            nextPlayer.currentVote = [ws1.cell(8,i+2).value[:-1],None]
            nextPlayer.currentVote[0] = int(nextPlayer.currentVote[0])
        else:
            nextPlayer.currentVote = ws1.cell(8, i+2).value.split(',')
            nextPlayer.currentVote[0] = int(nextPlayer.currentVote[0])
            nextPlayer.currentVote[1] = int(nextPlayer.currentVote[1])
        nextPlayer.online = ws1.cell(9, i+2).value
        for j in range(game.globalTurn):
            if ws2.cell(j+3, i+6).value[-1] == ',':
                nextPlayer.voteHistory[j] = [ws2.cell(j+3,i+6).value[:-1],None]
            else:
                nextPlayer.voteHistory[j] = ws2.cell(j+3, i+6).value.split(',')
                nextPlayer.voteHistory[j][1] = int(nextPlayer.voteHistory[j][1])
            nextPlayer.voteHistory[j][0] = int(nextPlayer.voteHistory[j][0])
        j = 12
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

    if game.state == 1:
        global proposalTask
        proposalTask = asyncio.create_task(proposalTimeLimit())
    elif game.state == 2:
        global voteTask
        voteTask = asyncio.create_task(votingTimeLimit())

setup = False
@bot.event
async def on_ready():
    try:
        if setup: return
    except:
        pass
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
    roleNames = ['Game State: Waiting', 'Game State: Proposing', 'Game State: Voting']
    await botMember.add_roles(get(nomicServer.roles, name=roleNames[game.state]))

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

~transmute
Toggles whether or not the current proposal involves transmutation
Called by the current player in #voting during the voting phase

~yes/no
Votes for or against the current proposal
Called by players in #voting during the voting phase
```"""

@bot.command()
async def help(ctx):
    await ctx.author.send(helpText)

@bot.command()
async def save(ctx):
    await saveData()

@bot.command()
async def data(ctx):
    await saveData()
    await botChannel.send(file=discord.File('nomic.xlsx'))



@bot.command()
async def join(ctx):
    global players
    if ctx.channel != botChannel:
        return
    player = get(players, discord=ctx.author)
    if player is not None:
        #When the author is/was part of the game
        index = players.index(get(players, discord=ctx.author))
        if player.active:
            await botChannel.send("You are already a player")
        return
    #New Player
    await botChannel.send("{} has joined the game!".format(ctx.author.mention))
    await ctx.author.add_roles(playerRole)
    newPlayerObj = Player(ctx.author, game.globalTurn)
    newPlayerObj.lastMessage = dt.datetime.now()
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
    while not players[i-1].active:
        i -= 1
        if i == -1:
            i = len(players) -1
    before = players[i-1].discord.display_name
    i = placement
    if i == len(players)-1:
        i = -1
    while not players[i+1].active:
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
    if index <= game.turn and not (game.globalTurn == 1 and game.state == 0):
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
    await updateChannel.send("Turn #{}! {}'s turn has begun, make a proposal using ~propose".format(game.globalTurn+1, players[game.turn].discord.mention))
    await players[game.turn].discord.add_roles(get(nomicServer.roles, name='Current Player'))
    await players[game.turn].discord.remove_roles(get(nomicServer.roles, name='Next Player'))
    await botMember.add_roles(get(nomicServer.roles, name='Game State: Proposing'))
    await botMember.remove_roles(get(nomicServer.roles, name='Game State: Waiting'))
    #Begin timer for proposing
    game.timerEnd = dt.datetime.now() + dt.timedelta(seconds = game.proposalTime)
    global proposalTask
    proposalTask = asyncio.create_task(proposalTimeLimit())
    await saveData()



async def proposalTimeLimit():
    now = dt.datetime.now()
    if (game.timerEnd - now).total_seconds() > 3601:
        await asyncio.sleep((game.timerEnd - now).total_seconds() -3600)
        await votingChannel.send("{}, you have one hour left to propose".format(players[game.turn].discord.mention))
        await asyncio.sleep(3600)
        await updateChannel.send("A proposal was not made in time, waiting for the next turn")
    else:
        await asyncio.sleep((game.timerEnd - now).total_seconds())
        await updateChannel.send("A proposal was not made in time, waiting for the next turn")
    await endTurn(0, 3)

async def votingTimeLimit():
    global game
    now = dt.datetime.now()
    if (game.timerEnd - now).total_seconds() > 3601:
        await asyncio.sleep((game.timerEnd - now).total_seconds() -3600)
        toVoteRole = get(nomicServer.roles, name='To Vote')
        await votingChannel.send("{}, you have one hour left to vote".format(toVoteRole.mention))
        await asyncio.sleep(3600)
        await votingChannel.send("Voting time is up")
    else:
        await asyncio.sleep((game.timerEnd - now).total_seconds())
        await votingChannel.send("Voting time is up")
    game.lastVote = None
    await checkVotes(1)

@bot.command()
async def timeout(ctx):
    if not(get(nomicServer.roles, name='Historian') in ctx.author.roles and ctx.channel == botChannel): return
    if game.state == 1:
        await updateChannel.send("A proposal was not made in time, waiting for the next turn")
        global proposalTask
        proposalTask.cancel()
        await endTurn(0, 3)
    elif game.state == 2:
        await votingChannel.send("Voting time is up")
        game.lastVote = None
        global voteTask
        voteTask.cancel()
        await checkVotes(1)



@bot.command()
async def propose(ctx):
    global players, game
    game.transmute = 0
    if not (ctx.channel == votingChannel and game.state == 1 and ctx.author == players[game.turn].discord):
        return
    #FirstVote is whether or not the first vote has been made yet, lastVote is the index of the most recent vote
    game.firstVote = False
    game.lastVote = None
    toVoteRole = get(nomicServer.roles, name='To Vote')
    for player in players:
        if player.active:
            player.currentVote = [0,None]
            await player.discord.add_roles(toVoteRole)
        else:
            player.currentVote = [-2,None]
    game.voteNumber = 0
    players[game.turn].stats['proposals'] += 1
    #End timer
    global proposalTask
    proposalTask.cancel()
    #Begin voting phase
    game.state = 2
    instant = math.ceil(sum([x.active for x in players])*game.yesProportion[game.transmute])
    txt = "{} {}'s proposal is available to vote on!\nVote with ~yes or ~no\n{} yes votes will instantly pass the proposal, {} are required to fail it"
    txt = txt.format(playerRole.mention, ctx.author.display_name, instant, sum([x.active for x in players]) + 1 - instant)
    await votingChannel.send(txt)
    #Give roles
    await botMember.add_roles(get(nomicServer.roles, name='Game State: Voting'))
    await botMember.remove_roles(get(nomicServer.roles, name='Game State: Proposing'))
    #Begin voting timer
    global voteTask
    game.timerEnd = dt.datetime.now() + dt.timedelta(seconds = game.votingTime)
    voteTask = asyncio.create_task(votingTimeLimit())
    await saveData()

@bot.command()
async def transmute(ctx):
    global game
    if not (ctx.channel == votingChannel and game.state == 2 and (ctx.author == players[game.turn].discord) or get(nomicServer.roles,name='Historian') in ctx.author.roles):
        return
    await votingChannel.send('This proposal involves transmutation! Unanimity is required to pass')
    game.transmute = 1



@bot.command()
async def yes(ctx):
    global players, game
    if not (ctx.channel == votingChannel and game.state == 2 and ctx.author in [x.discord for x in players]):
        return
    player = get(players, discord = ctx.author)
    if player.currentVote[0] == 0:
        player.currentVote = [1,game.voteNumber]
        game.voteNumber += 1
        await votingChannel.send("{} has voted!".format(ctx.author.display_name))
        toVoteRole = get(nomicServer.roles, name='To Vote')
        await ctx.author.remove_roles(toVoteRole)
    elif player.currentVote[0] != -2:
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
    if player.currentVote[0] == 0:
        player.currentVote = [2,game.voteNumber]
        game.voteNumber += 1
        await votingChannel.send("{} has voted!".format(ctx.author.display_name))
        toVoteRole = get(nomicServer.roles, name='To Vote')
        await ctx.author.remove_roles(toVoteRole)
    elif player.currentVote[0] != -2:
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
        if player.currentVote[0] == 0 and player.active:
            allVotes = False
        elif player.currentVote[0] == 1: yesses += 1
        elif player.currentVote[0] == 2: nos += 1
    if not timeUp:
        global summaryMsgID
        try:
            summaryMsg = await votingChannel.fetch_message(summaryMsgID)
            await summaryMsg.delete()
        except:
            pass
        txt = 'Current votes for/against are {}/{}   ({}%/{}%)\n{}% of all players have voted yes, {}% of all players have voted no'
        txt = txt.format(yesses, nos, round(yesses*100/(yesses+nos),2), round(nos*100/(yesses+nos),2), round(yesses*100/sum([x.active for x in players]),2), round(nos*100/sum([x.active for x in players]),2))
        summaryMsg = await votingChannel.send(txt)
        summaryMsgID = summaryMsg.id

    #All votes have been cast
    if allVotes:
        if yesses/(yesses+nos) >= game.yesProportion[game.transmute] - 0.001:
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
        elif yesses/(yesses+nos) >= game.timeoutProportion[game.transmute] - 0.001 and (yesses + nos)/sum([x.active for x in players]) >= game.timeoutMinimum[game.transmute] - 0.001:
            await updateChannel.send("Voting time is up, and the proposal has passed. Waiting for the next turn to start")
            await endTurn(1, 2)
        else:
            await updateChannel.send("Voting time is up, and the proposal has failed. Waiting for the next turn to start")
            await endTurn(0, 2)
        return
    #Enough votes to determine a conclusion
    if yesses/sum([x.active for x in players]) >= game.yesProportion[game.transmute] - 0.001:
        await updateChannel.send("There are enough yes votes for the proposal to pass. Waiting for the next turn to start")
        await endTurn(1, 1)
    if nos/sum([x.active for x in players]) > (1-game.yesProportion[game.transmute]) + 0.001:
        await updateChannel.send("There are enough no votes for the proposal to fail. Waiting for the next turn to start")
        await endTurn(0, 1)



async def endTurn(success, endCondition):
    global players, game, summaryMsgID
    game.state = 0
    game.timerEnd = None
    #Points
    yesses = 0
    nos = 0
    for player in players:
        if player.currentVote[0] == 1: yesses += 1
        elif player.currentVote[0] == 2: nos += 1
    summaryMsgID = None
    if endCondition != 3:
        txt = 'Final Votes: {}/{}   ({}%/{}%)   out of {} players'.format(yesses, nos, round(yesses*100/(yesses+nos),2), round(nos*100/(yesses+nos),2), sum([x.active for x in players]))
        await updateChannel.send(txt)
        await votingChannel.send('Voting is now over')
    if success:
        pointAdd = 0
        for player in players:
            if player.currentVote[0] == 1:
                pointAdd += 2
            elif player.currentVote[0] == 2:
                player.points += 5
        players[game.turn].points += pointAdd
        await updateChannel.send('Point changes:')
        await updateChannel.send('+{}: {}'.format(pointAdd,players[game.turn].discord.display_name))
        ioptns = '+5: '
        for player in players:
            if player.currentVote[0] == 2:
                ioptns += player.discord.display_name + '   '
        if len(ioptns) >= 5:
            await updateChannel.send(ioptns)
    elif endCondition != 3:
        players[game.turn].points -= 10
        await updateChannel.send('Point changes:')
        await updateChannel.send('-10: ' + players[game.turn].discord.display_name)

    if endCondition != 2 and endCondition != 3:
        global voteTask
        voteTask.cancel()
    if endCondition == 3:
        global proposalTask
        proposalTask.cancel()

    #Remove roles
    toVoteRole = get(nomicServer.roles, name='To Vote')
    await players[game.turn].discord.remove_roles(get(nomicServer.roles, name='Current Player'))
    for player in players:
        await player.discord.remove_roles(toVoteRole)
    await botMember.add_roles(get(nomicServer.roles, name='Game State: Waiting'))
    await botMember.remove_roles(get(nomicServer.roles, name='Game State: Proposing'))
    await botMember.remove_roles(get(nomicServer.roles, name='Game State: Voting'))
    if game.lastVote is not None:
        game.lastVote.stats['lastVotes'] += 1

    #Begin waiting phase
    turn = Turn(game.globalTurn)
    turn.proponent = players[game.turn].discord
    turn.passed = success
    turn.end = endCondition
    for player in players:
        player.voteHistory.append(player.currentVote)
        player.currentVote = [None,None]
        if player.active:
            await checkActive(player)
    game.state = 0
    game.firstVote = False
    game.lastVote = None
    game.voteNumber = None
    turns.append(turn)
    
    game.turn += 1
    game.globalTurn += 1
    if game.turn >= len(players):
        game.turn = 0
    while not players[game.turn].active:
        game.turn += 1
        if game.turn > len(players):
            game.turn = 0

    await players[game.turn].discord.add_roles(get(nomicServer.roles, name='Next Player'))
    await saveData()



async def saveData():
    ws3['B1'] = len(players)
    ws3['B3'] = game.turn
    ws3['B4'] = game.globalTurn
    ws3['B5'] = game.state
    ws3['B9'] = game.voteNumber
    ws3['B16'] = game.transmute
    ws3['B17'] = game.timerEnd
    if summaryMsgID: ws3['B19'] = str(summaryMsgID)
    else: ws3['B19'] = None
    for player in players:
        i = players.index(player)
        if player.discord in nomicServer.members:
            ws1.cell(1, i+2, player.discord.display_name)
            ws2.cell(1, i+6, player.discord.display_name)
            ws1.cell(2, i+2, player.discord.name)
            ws1.cell(3, i+2, str(player.discord.id))
        ws1.cell(5, i+2, player.active)
        ws1.cell(6, i+2, player.lastMessage)
        ws1.cell(7, i+2, player.points)
        if player.currentVote[0] is None:
            ws1.cell(8, i+2).value = None
        elif player.currentVote[1] is None:
            ws1.cell(8, i+2, str(player.currentVote[0]) + ',')
        else:
            ws1.cell(8, i+2, str(player.currentVote[0]) + ',' + str(player.currentVote[1]))
        ws1.cell(9, i+2, player.online)
    ws3['B7'] = game.firstVote
    if game.lastVote is not None:
        ws3['B8'] = str(game.lastVote.discord.id)
    else: ws3['B8'] = None

    for i in range(game.globalTurn):
        for player in players:
            if player.voteHistory[i][1] is None and player.voteHistory[i][0] is not None:
                ws2.cell(i+3, players.index(player)+6, str(player.voteHistory[i][0]) + ',')
            elif player.voteHistory[i][0] is not None:
                ws2.cell(i+3, players.index(player)+6, str(player.voteHistory[i][0]) + ',' + str(player.voteHistory[i][1]))
        ws2.cell(i+3, 1, turns[i].turnNumber)
        proponent = turns[i].proponent
        if not isinstance(proponent, str):
            ws2.cell(i+3, 2, str(proponent.id))
            ws2.cell(i+3, 3, proponent.display_name)
        ws2.cell(i+3, 4, turns[i].passed)
        ws2.cell(i+3, 5, turns[i].end)
    for player in players:
        i = 12
        for stat in player.stats.values():
            ws1.cell(i, players.index(player)+2, stat)
            i += 1

    wb.save('nomic.xlsx')
    print("Saved " + str(dt.datetime.now()))



@bot.event
async def on_message(ctx):
    if ctx.author in [x.discord for x in players]:
        player = get(players, discord = ctx.author)
        player.lastMessage = dt.datetime.now()
        if ctx.content[0] != '~':
            player.stats['messages'] += 1
            if not player.online:
                player.online = True
    try:
        if ctx.content[:2] == '~#' and int(ctx.content[2:]):
            i = 1
            while ws4.cell(i,1).value is not None:
                if ws4.cell(i,1).value == int(ctx.content[2:]):
                    await ctx.channel.send(ws4.cell(i,2).value)
                    return
                i += 1
            await ctx.channel.send('Fool')
            return
    except:
        pass
    await bot.process_commands(ctx)


async def daily():
    global players
    #Loops once per day
    while True:
        tomorrow = dt.date.today() + dt.timedelta(days=1)
        midnight = dt.datetime.combine(tomorrow, dt.time.min)
        #Loops once per hour
        while True:
            now = dt.datetime.now()
            difference = (midnight-now).total_seconds()
            for player in players:
                if player.active:
                    await checkActive(player)
            if difference < 3600:
                break
            await asyncio.sleep(3600)
            await saveData()
        await asyncio.sleep(difference + 60)
        for player in players:
            if player.active:
                player.stats['daysPlaying'] += 1
            if player.online:
                player.stats['daysOnline'] += 1
                player.online = False
        await saveData()



async def checkActive(player):
    if (dt.datetime.now() - player.lastMessage).total_seconds() < 259200:
        return
    for i in range(game.globalTurn-3, game.globalTurn):
        if player.voteHistory[i][0] is not 0:
            return
    await botChannel.send('{} has been made inactive, use ~resurrect to rejoin the game'.format(player.discord.display_name))
    player.active = False

@bot.command()
async def cryosleep(ctx):
    if not (ctx.author in [x.discord for x in players] and ctx.channel == botChannel):
        return
    player = get(nomicServer.players, discord=ctx.author)
    if player.active:
        player.active = False
        await botChannel.send('You\'ve been made inactive, use ~resurrect to rejoin the game')
        await player.remove_roles(playerRole)
        await player.add_roles(get(nomicServer.roles, name='Inactive Player'))
        if game.state == 2:
            player.currentVote[0] = -2
            player.remove_roles(get(nomicServer.roles, name='To Vote'))

@bot.command()
async def resurrect(ctx):
    if not (ctx.author in [x.discord for x in players] and ctx.channel == botChannel):
        return
    player = get(nomicServer.players, discord=ctx.author)
    if not player.active:
        player.active = True
        await botChannel.send('You\'ve rejoined the game!')
        await player.add_roles(playerRole)
        await player.remove_roles(get(nomicServer.roles, name='Inactive Player'))
        if game.state == 2:
            player.currentVote[0] = 0
            player.add_roles(get(nomicServer.roles, name='To Vote'))

players = []
bot.loop.create_task(daily())

bot.run(token)