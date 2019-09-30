import discord
from discord.ext import commands
from discord.utils import get
import random
import openpyxl
import asyncio
import datetime as dt

#token.txt is a file not uploaded to git, containing the bot token and server name
with open("token.txt", 'r') as f:
    token = f.readline()[:-1]
    serverName = f.readline()

client = discord.Client()
bot = commands.Bot(command_prefix='~')
bot.remove_command('help')

#Excel sheets
wb = openpyxl.load_workbook('Nomic.xlsx')
ws1 = wb['Players']
ws2 = wb['Turns']
ws3 = wb['Misc']

'''
Players is a list of all players in turn order. This turn order is used for all other lists
Includes players who have left the game, so that if they rejoin they retain the same stats

StillPlaying is a list of whether or not a player is still playing
0 : No longer playing
1 : Current player

VoteHistory is an array where each row is one turn, and each column is the vote from each player
0 : Non-vote
1 : Yes
2 : No
-1 : Forfeit
The third to last column is the player id of the proponent
The second to last column is whether or not the proposal passed
0 : Failed   1 : Passed
The last column is the global turn

Turn is the index of the current players turn, or the next player in the case where the game is between turns
It skips players who have left the game, and loops back to 0
globalTurn is the actual turn of the game. It only increments by 1

State is an integer describing what part of the turn the game is in. Many commands only work during specific states
0 : The previous turn has ended, and the bot is waiting for historians to formalise the end of the turn and start the next
1 : The current player is writing a proposal to to be discussed and voted on
2 : A proposal has been made and player can vote for it



Stats is an array where each row is a different stat being tracked, and each column is a player in turn order
0 : Total messages sent
1 : Total number of days as a player
2 : Total number of days online as a player
3 : Total number of proposals made
Daily stats are updated at the end of the day



The following variables reset each turn
Votes is a list of what each player has voted, in turn order
0 : Non-vote
1 : Yes
2 : No
-1 : Forfeit
-2 : Non-player

Yesses is the number of yes votes for the current proposal
Nos is the number of no votes for the current proposal
'''


@bot.event
async def on_ready():
    global nomicServer, botMember, generalChannel, votingChannel, playerRole
    #Commonly used channels and roles
    nomicServer = get(bot.guilds, name=serverName)
    botMember = get(nomicServer.members, id=376215780083367936)

    generalChannel = get(nomicServer.channels, name='general')
    votingChannel = get(nomicServer.channels, name='voting')

    playerRole = get(nomicServer.roles, name='Player')

    #Load excel data
    global turn, globalTurn, state, players, stillPlaying, voteHistory, stats, votes, yesses, nos, proposalTime, votingTime, yesProportion, online
    numPlayers = ws3['B1'].value
    turn = ws3['B3'].value
    globalTurn = ws3['B4'].value
    state = ws3['B5'].value
    proposalTime = ws3['B13'].value
    votingTime = ws3['B14'].value
    yesProportion = ws3['B16'].value

    players = []
    stillPlaying = []
    votes = []
    yesses = 0
    nos = 0
    for i in range(numPlayers):
        players.append(get(nomicServer.members, id=int(ws1.cell(3, i+2).value)))
        if players[i] == None:
            players[i] = ws1.cell(1, i+2).value
        stillPlaying.append(ws1.cell(5, i+2).value)
        if ws3['B9'].value == 0:
            votes.append(ws3.cell(8, i+2).value)
            if votes[i] == 1:
                yesses += 1
            elif votes[i] == 2:
                nos += 1

    voteHistory = []
    for i in range(globalTurn):
        turnVotes = []
        for j in range(numPlayers + 2):
            turnVotes.append(ws2.cell(i+4, j+2).value)
        proponent = get(nomicServer.members, id=int(turnVotes[numPlayers]))
        if proponent is not None:
            turnVotes[numPlayers+1] = proponent.display_name
        voteHistory.append(turnVotes + [i])

    stats = []
    for i in range(ws3['B11'].value):
        statRow = []
        for j in range(numPlayers):
            statRow.append(ws1.cell(i+8, j+2).value)
        stats.append(statRow)
    bot.loop.create_task(daily())

    online = []
    for i in range(numPlayers):
        online.append(ws3.cell(7, i+2))

    #Initial state role
    await bot.change_presence(activity=discord.Game(name='~help'))
    for role in nomicServer.roles:
        if role.name.startswith('Game State :'):
            await role.delete()
    roleNames = ['Game State : Waiting', 'Game State : Proposing', 'Game State : Voting']
    newRole = await nomicServer.create_role(name=roleNames[state], colour=discord.Colour(0x992d22), hoist=True)
    await botMember.add_roles(newRole)

    print("Bot is ready")


helpText = """```
~help
Displays this message

~join
Gives a non-player the player role and adds them into the turn order in a random position
Called by non-players in #general at any time

~ready
Causes the game to move from a state of waiting to the start of the next turn
Called by historians in #general during the waiting phase

~propose
Begins the voting process once the current player has made a proposal
Called by the current player in #voting during the proposal phase

~yes/no
Votes for or against the current proposal
Called by players during the voting phase

~tz
Gives the user a time zone role
One argument *X, where * is either + or -, and X is <= 13, except for -0
A player can only have one time zone role, and the bot can create these roles when they don't exist, and delete them when there are no longer any users
Called by anyone in #general at any time
```"""

@bot.command()
async def help(ctx):
    await ctx.author.send(helpText)


@bot.command(name='join')
async def joinGame(ctx):
    global players
    if ctx.channel == generalChannel:
        try:
            #When the author is/was part of the game
            index = players.index(ctx.author)
            if stillPlaying[index] == 1:
                await generalChannel.send("You are already a player")
            else:
                stillPlaying[index] = 1
                await generalChannel.send(ctx.author.mention + " has rejoined the game!")
                #Find the players before and after in the turn order who are still playing
                i = index
                while stillPlaying[i-1] == 0:
                    i -= 1
                    if i == -1:
                        i = len(players) -1
                before = players[i-1].display_name
                i = index
                while stillPlaying[i+1] == 0:
                    i += 1
                    if i == len(players)-1:
                        i = -1
                after = players[i+1].display_name
                await generalChannel.send("You are player #" + str(index+1) + ' in the turn order, between ' + before + ' & ' + after)
            return
        except:
            pass
        #New Player
        await generalChannel.send(ctx.author.mention + " has joined the game!")
        await ctx.author.add_roles(playerRole)
        if len(players) == 0:
            newPlayer(0, ctx.author)
            return
        #Pick a random place to insert the player into
        placement = random.randint(0,len(players)-1)
        if placement == 0 and random.randint(0,1) == 0:
            #The first and last position are equivalent, so there is a 50% chance of each
            placement == len(players)
        newPlayer(placement, ctx.author)
        #Find the players before and after who are still part of the game
        i = placement
        while stillPlaying[i-1] == 0:
            i -= 1
            if i == -1:
                i = len(players) -1
        before = players[i-1].display_name
        i = placement
        if i == len(players)-1:
            i = -1
        while stillPlaying[i+1] == 0:
            i += 1
            if i == len(players)-1:
                i = -1
        after = players[placement+1].display_name
        if len(players) > 1:
            await generalChannel.send("You are player #" + str(placement+1) + ' in the turn order, between ' + before + ' & ' + after)

def newPlayer(index, player):
    global players, stillPlaying, voteHistory, stats, turn
    #If the new player is before the current player, increment turn unless the game hasn't started yet
    if index <= turn and not (globalTurn == 0 and state == 0):
        turn += 1
    #Update lists
    if index == len(players):
        #When the player is placed at the end of the list
        players = players + [player]
        stillPlaying = stillPlaying + [1]
        for i in range(len(voteHistory)):
            voteHistory[i] = voteHistory[i] + [-2]
        for i in range(len(stats)):
            stats[i] = stats[i] + [0]
        if state == 2:
            votes = votes + [-2]
        online = online + [0]
        return
    #Update lists
    players = players[:index] + [player] + players[index:]
    stillPlaying = stillPlaying[:index] + [1] + stillPlaying[index:]
    for i in range(len(voteHistory)):
        voteHistory[i] = voteHistory[:index] + [-2] + voteHistory[index:]
    for i in range(len(stats)):
        stats[i] = stats[i][:index] + [0] + stats[i][index:]
    if state == 2:
        votes = votes[:index] + [-2] + votes[index:]
    online = online[:index] + [0] + online[index:]


@bot.command(name='ready')
async def startTurn(ctx):
    global state
    if ctx.channel == generalChannel and state == 0:
        #Begin the proposal phase
        state = 1
        #Give roles
        await votingChannel.send(players[turn].mention + "'s turn has begun, make a proposal using !propose")
        currentPlayerRole = get(nomicServer.roles, name='Current Player')
        await players[turn].add_roles(currentPlayerRole)
        newRole = await nomicServer.create_role(name='Game State : Proposing', colour=discord.Colour(0x992d22), hoist=True)
        await botMember.add_roles(newRole)
        oldRole = get(nomicServer.roles, name='Game State : Waiting')
        await oldRole.delete()
        #Begin timer for proposing
        global proposalTask
        proposalTask = asyncio.create_task(proposalTimeLimit())

async def proposalTimeLimit():
    await asyncio.sleep(proposalTime -3600)
    await votingChannel.send(players[turn].mention + ", you have one hour left to propose")
    await asyncio.sleep(3600)
    await votingChannel.send("A proposal was not made in time, starting next turn")
    await endTurn(0)


@bot.command(name='propose')
async def startVote(ctx):
    global state, yesses, nos, votes
    if ctx.channel == votingChannel and state == 1:
        #Reset variables for voting
        yesses = 0
        nos = 0
        votes = [0] * len(players)
        for i in range(len(players)):
            if stillPlaying[i] == 0:
                votes[i] = -2
        #End timer
        global proposalTask
        proposalTask.cancel()
        #Begin voting phase
        state = 2
        await votingChannel.send(playerRole.mention + " " + ctx.author.display_name + "'s proposal is available to vote on")
        #Give roles
        for i in range(len(players)):
            if stillPlaying[i] == 1:
                toVoteRole = get(nomicServer.roles, name='To Vote')
                await players[i].add_roles(toVoteRole)
        newRole = await nomicServer.create_role(name='Game State : Voting', colour=discord.Colour(0x992d22), hoist=True)
        await botMember.add_roles(newRole)
        oldRole = get(nomicServer.roles, name='Game State : Proposing')
        await oldRole.delete()
        stats[3][turn] += 1
        #Begin voting timer
        global voteTask
        voteTask = asyncio.create_task(votingTimeLimit())

async def votingTimeLimit():
    await asyncio.sleep(votingTime -3600)
    toVoteRole = get(nomicServer.roles, name='To Vote')
    await votingChannel.send(toVoteRole.mention + ", you have one hour left to vote")
    await asyncio.sleep(3600)
    await votingChannel.send("Voting time is up")
    await checkVotes(1)


@bot.command(name='yes')
async def voteYes(ctx):
    global yesses, votes
    if ctx.channel == votingChannel and state == 2:
        i = players.index(ctx.author)
        if votes[i] == 0:
            votes[i] = 1
            yesses += 1
            await votingChannel.send(ctx.author.display_name + " has voted!")
            toVoteRole = get(nomicServer.roles, name='To Vote')
            await ctx.author.remove_roles(toVoteRole)
        else:
            await votingChannel.send("You've already voted")
        await checkVotes(0)

@bot.command(name='no')
async def voteNo(ctx):
    global nos, votes
    if ctx.channel == votingChannel and state == 2:
        i = players.index(ctx.author)
        if votes[i] == 0:
            votes[i] = 2
            nos += 1
            await votingChannel.send(ctx.author.display_name + " has voted!")
            toVoteRole = get(nomicServer.roles, name='To Vote')
            await ctx.author.remove_roles(toVoteRole)
        else:
            await votingChannel.send("You've already voted")
        await checkVotes(0)

async def checkVotes(timeUp):
    global state, turn
    allVotes = True
    for i in range(len(votes)):
        if votes[i] == 0 and stillPlaying[i] == 1:
            allVotes = False
    #All votes have been cast
    if allVotes:
        if yesses/(yesses+nos) >= yesProportion:
            await generalChannel.send("All votes have been cast and the proposal has passed. Waiting for the next turn to start")
            success = 1
        else:
            await generalChannel.send("All votes have been cast and the proposal has failed. Waiting for the next turn to start")
            success = 0
        await endTurn(success)
        return
    #Time is up
    if timeUp:
        if yesses + nos == 0:
            await generalChannel.send("The proposal has failed as no votes were cast, waiting for the next turn to start")
            success = 0
        elif yesses/(yesses+nos) >= yesProportion:
            await generalChannel.send("Voting time is up, and the proposal has passed. Waiting for the next turn to start")
            success = 1
        else:
            await generalChannel.send("Voting time is up, and the proposal has failed. Waiting for the next turn to start")
            success = 0
        await endTurn(success)
        return
    #Enough votes to determine a conclusion
    if yesses/sum(stillPlaying) >= yesProportion:
        generalChannel.send("There are enough yes votes for the proposal to pass. Waiting for the next turn to start")
        await endTurn(1)
    if nos/sum(stillPlaying) > (1-yesProportion):
        generalChannel.send("There are enough no votes for the proposal to fail. Waiting for the next turn to start")
        await endTurn(0)


async def endTurn(success):
    global state, turn, globalTurn, voteHistory
    #Remove roles
    currentPlayerRole = get(nomicServer.roles, name='Current Player')
    await players[turn].remove_roles(currentPlayerRole)
    i = 0
    for player in players:
        if stillPlaying[i] == 1:
            toVoteRole = get(nomicServer.roles, name='To Vote')
            await player.remove_roles(toVoteRole)
        i += 1
    for role in nomicServer.roles:
        if role.name.startswith('Game State :'):
            await role.delete()
    newRole = await nomicServer.create_role(name='Game State : Waiting', colour=discord.Colour(0x992d22), hoist=True)
    await botMember.add_roles(newRole)
    #Begin waiting phase
    voteHistory.append(votes + [str(players[turn].id), players[turn].display_name, success, globalTurn])
    state = 0
    turn += 1
    globalTurn += 1
    if turn >= len(players):
        turn = 0
    while stillPlaying[turn] == 0:
        turn += 1
        if turn > len(players):
            turn = 0
    await saveData()


async def saveData():
    ws3['B1'] = len(players)
    ws3['B3'] = turn
    ws3['B4'] = globalTurn
    ws3['B5'] = state
    for i in range(len(players)):
        if stillPlaying[i] == 1:
            ws1.cell(1, i+2, players[i].display_name)
            ws2.cell(1, i+2, players[i].display_name)
            ws1.cell(2, i+2, players[i].name)
            ws1.cell(3, i+2, str(players[i].id))
        ws1.cell(5, i+2, stillPlaying[i])
        if votes == []:
            ws3.cell(8, i+2, None)
            ws3['B9'] = 1
        else:
            ws3.cell(8, i+2, votes[i])
            ws3['B9'] = 0
        ws3.cell(7, i+2, online[i])

    for i in range(globalTurn):
        for j in range(len(players)+3):
            ws2.cell(i+4, j+2, voteHistory[i][j])
        ws2.cell(i+4, 1, i)
    for i in range(ws3['B10'].value):
        for j in range(len(players)):
            ws1.cell(i+8, j+2, stats[i][j])
    wb.save('Nomic.xlsx')
    print("Saved")



@bot.command(name='tz')
async def timeZoneRole(ctx, tz):
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



@bot.event
async def on_message(ctx):
    index = players.index(ctx.author)
    stats[0][index] += 1

async def daily():
    global online
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    midnight = dt.datetime.combine(tomorrow, dt.time.min)
    #Loops until midnight in whichever timezone the bot is run in
    while True:
        now = dt.datetime.now()
        difference = (midnight-now).total_seconds()
        for i in range(len(online)):
            if stillPlaying[i] == 1 and online[i] == 0:
                if players[i].status == "online":
                    online[i] == 1
        saveData()
        if difference < 3600:
            break
        await asyncio.sleep(3600)
    for i in range(len(players)):
        if stillPlaying[i] == 1:
            stats[1][i] += 1
        if online[i] == 1:
            stats[2][i] += 1
    #Wait an hour in case of daylight savings
    await asyncio.sleep(difference + 3610)

bot.run(token)