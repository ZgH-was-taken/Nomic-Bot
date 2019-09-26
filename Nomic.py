import os
import discord
from discord.ext import commands
from discord.utils import get
import random
from dotenv import load_dotenv
load_dotenv()

f = open("token.txt", 'r')
token = f.readline()[:-1]
server = f.readline()
f.close()

client = discord.Client()
bot = commands.Bot(command_prefix='!')

@bot.command(name='join')
async def joinGame(ctx):
    global players, turns
    if ctx.channel.name == "general":
        players.append(ctx.author)
        await ctx.channel.send(players[-1].mention + " has joined the game!")
        playerRole = get(ctx.guild.roles, name = 'Player')
        await ctx.author.add_roles(playerRole)
        if len(turns) == 0:
            turns.append(ctx.author)
        else:
            placement = random.randint(0,len(turns)-1)
            turns = turns[:placement] + [ctx.author] + turns[placement:]
            before = turns[placement-1].display_name
            after = turns[placement+1].display_name
            await ctx.channel.send("You are player #" + str(placement+1) + ' in the turn order, between ' + before + ' & ' + after)

@bot.command(name='tz')
async def timeZoneRole(ctx, tz):
    if not ((tz[0] == '+' or tz[0] == '-') and int(tz[1:]) <= 13 and tz != '-0' and ctx.channel.name == 'general'):
        return
    newRole = get(ctx.guild.roles, name = 'Time Zone ' + tz)
    if newRole is None:
        newRole = await ctx.guild.create_role(name = 'Time Zone ' + tz)
    for role in ctx.author.roles:
        if role.name.startswith('Time Zone '):
            if role.name.endswith(tz):
                if len(role.members) == 1:
                    await role.delete()
                else:
                    await ctx.author.remove_roles(role)
            else:
                if len(role.members) == 1:
                    await role.delete()
                else:
                    await ctx.author.remove_roles(role)
                await ctx.author.add_roles(newRole)
            return
    await ctx.author.add_roles(newRole)

@bot.command(name='ready')
async def startTurn(ctx):
    global state, yesses, nos, votes
    if ctx.channel.name == 'general' and state == 'Between Turns':
        voting = get(ctx.guild.channels, name = 'voting')
        await voting.send(turns[turn].mention + "'s turn has begun, make a proposal using !propose")
        state = 'Proposing'
        yesses = 0
        nos = 0
        votes = [0] * len(turns)
        

@bot.command(name='propose')
async def startVote(ctx):
    global state
    if ctx.channel.name == 'voting' and state == 'Proposing':
        state = 'Voting'
        playerRole = get(ctx.guild.roles, name = 'Player')
        await ctx.channel.send(playerRole.mention + " " + ctx.author.display_name + "'s proposal is available to vote on")

@bot.command(name='yes')
async def voteYes(ctx):
    global yesses, votes
    if ctx.channel.name == 'voting' and state == 'Voting':
        for i in range(len(turns)):
            if turns[i] == ctx.author:
                break
        if votes[i] == 0:
            votes[i] = 1
            yesses += 1
            await ctx.channel.send(ctx.author.display_name + " has voted!")
        else:
            await ctx.channel.send("You've already voted")
        await checkVotes()

@bot.command(name='no')
async def voteNo(ctx):
    global nos, votes
    if ctx.channel.name == 'voting' and state == 'Voting':
        for i in range(len(turns)):
            if turns[i] == ctx.author:
                break
        if votes[i] == 0:
            votes[i] = -1
            nos += 1
            await ctx.channel.send(ctx.author.display_name + " has voted!")
        else:
            await ctx.channel.send("You've already voted")
        await checkVotes()

async def checkVotes():
    global state, turn
    allVotes = True
    for i in range(len(votes)):
        if votes[i] == 0:
            allVotes = False
    guild = get(bot.guilds, name=server)
    general = get(guild.channels, name='general')
    if allVotes:
        if yesses >= nos:
            await general.send("The proposal has passed, waiting for the next turn to start")
        else:
            await general.send("The proposal has failed, waiting for the next turn to start")
        state = 'Between Turns'
        turn += 1
        if turn >= len(turns):
            turn = 0
        return
    if yesses >= 2:
        general.send("The proposal has passed, waiting for the next turn to start")
        state = 'Between Turns'
        turn += 1
        if turn >= len(turns):
            turn = 0

@bot.command(name='timeUp')
async def checkVotesTimeUp(ctx):
    global state, turn
    guild = get(bot.guilds, name=server)
    general = get(guild.channels, name='general')
    if yesses >= nos:
        await general.send("The proposal has passed, waiting for the next turn to start")
    else:
        await general.send("The proposal has failed, waiting for the next turn to start")
    state = 'Between Turns'
    turn += 1
    if turn >= len(turns):
        turn = 0

players = []
turns = []
turn = 0
state = 'Between Turns'

yesses = 0
nos = 0
votes = []

bot.run(token)