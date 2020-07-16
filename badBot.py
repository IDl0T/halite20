# Contains all dependencies used in bot
# First file loaded

from kaggle_environments import make
from kaggle_environments.envs.halite.helpers import *
import math, random
import numpy as np
import scipy.optimize
import scipy.ndimage
from queue import PriorityQueue

# Global constants

    # All game state goes here - everything, even mundane
state = {}

    # Contains all weights to be initialized
    #TODO: Train!

weights = [
    # shipyard_reward weights - 0
    np.array([1,1,-1,0.5,0.2])
] 

def setWeight(v):
    global weights
    weights = v

# Init function - called at the start of each game
def init(board):
    global state
    state['configuration'] = board.configuration
    state['me'] = board.current_player_id
    state['playerNum'] = len(board.players)
    state['memory'] = {}
    pass

# Run start of every turn
def update(board):
    global action
    action = {}
    state['currentHalite'] = board.current_player.halite
    state['next'] = np.zeros((board.configuration.size,board.configuration.size))
    state['board'] = board
    state['memory'][board.step] = board
    state['cells'] = board.cells.values()
    state['ships'] = board.ships.values()
    state['myShips'] = board.current_player.ships
    state['shipyards'] = board.shipyards.values()
    state['myShipyards'] = board.current_player.shipyards

    # Calc processes
    encode()
# General random helper functions that are not strictly "process" or in "nav"

# Map from 0 to 1
def normalize(v):
    norm = np.linalg.norm(v,np.inf)
    if norm == 0: 
       return v
    return v / norm

def closest_ship(t):
    res = None
    for ship in state['myShips']:
        if res == None:
            res = ship
        elif dist(t,res.point) > dist(t,ship.point):
            res = ship
    return res


# optimus_mine helpers

MAX_CHASE_RANGE = 2
CHASE_PUNISHMENT = 2
SHIPYARD_DEMOLISH_REWARD = 700

OPTIMAL_MINING_TURNS = np.array( # optimal mining turn for [Cargo/Deposit, travelTime]
  [[0, 2, 3, 4, 4, 5, 5, 5, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 8],
   [0, 1, 2, 3, 3, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 7, 7, 7],
   [0, 0, 2, 2, 3, 3, 4, 4, 4, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 7],
   [0, 0, 1, 2, 2, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6],
   [0, 0, 0, 1, 2, 2, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 6],
   [0, 0, 0, 0, 0, 1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5],
   [0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4],
   [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3],
   [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2],
   [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
   [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])

def num_turns_to_mine(C, D, travelTime, minMineTurns=1): # https://www.kaggle.com/krishnaharish/optimus-mine-agent
    # How many turns should we plan on mining?
    # C = carried halite, D = halite deposit, travelTime = steps to square and back to shipyard
    travelTime = int(np.clip(travelTime, 0, OPTIMAL_MINING_TURNS.shape[1] - 1))
    if C == 0:
        cdRatio = 0
    elif D == 0:
        cdRatio = OPTIMAL_MINING_TURNS.shape[0] - 1
    else:
        cdRatio = np.clip(int(math.log(C/D)*2.5+5.5), 0, OPTIMAL_MINING_TURNS.shape[0] - 1)
    return max(OPTIMAL_MINING_TURNS[cdRatio, travelTime], minMineTurns)

def halite_per_turn(cargo, deposit, travelTime, minMineTurns=1):
    turns = num_turns_to_mine(cargo, deposit, travelTime, minMineTurns)
    mined = cargo + (1 - .75**turns) * deposit
    return mined / (travelTime + turns)

# Core strategy

action = {} #ship -> [value,ship,target]

def ship_tasks(): # return updated tasks
    global action
    cfg = state['configuration']
    board = state['board']
    me = board.current_player
    tasks = {}
    assign = []

    # Rule based
        # Run, return

    for ship in me.ships:
        # Run 
        for target in get_adjacent(ship.position):
            if board.cells[target].ship != None:
                targetShip = board.cells[target].ship
                if targetShip.player.id != state['me'] and targetShip.halite < ship.halite:
                    action[ship] = (math.inf,ship,state['closestShipyard'][ship.position.x][ship.position.y])

        if ship in action:
            continue

        # Return
        RETURN_THRESHOLD = 5
        if ship.halite > RETURN_THRESHOLD * state['haliteMean'] + board.cells[ship.position].halite: #TODO Optimize the return threshold
            action[ship] = (ship.halite,ship,state['closestShipyard'][ship.position.x][ship.position.y])

        if ship in action:
            continue
            
        assign.append(ship)

    # Reward based
        # Attack, Mine
    targets = []
    for i in board.cells.values(): # Filter targets
        if i.shipyard != None:
            continue
        if i.halite == 0 and i.ship == None:
            continue
        targets.append(i)
    rewards = np.zeros((len(assign), len(targets)))

    # TODO: Remove nested for loop
    for i,ship in enumerate(assign):
        for j,cell in enumerate(targets):
            rewards[i, j] = get_reward(ship,cell)

    rows, cols = scipy.optimize.linear_sum_assignment(rewards, maximize=True) # rows[i] -> cols[i]
    for r, c in zip(rows, cols):
        action[assign[r]] = (rewards[r][c],assign[r],targets[c].position)

    #TODO: Add shipyard attack
    #Process actions
    actions = list(action.values())
    actions.sort(reverse=True,key=lambda x : x[0])
    for act in actions:
        act[1].next_action = a_move(act[1],act[2],state[act[1]]['blocked'])
        # Ship convertion
        sPos = act[1].position 
        if state['closestShipyard'][sPos.x][sPos.y] == sPos and state['board'].cells[sPos].shipyard == None:
            act[1].next_action = ShipAction.CONVERT
    return

def spawn_tasks():
    shipyards = state['board'].current_player.shipyards
    shipyards.sort(reverse=True,key=lambda shipyard : state['haliteSpread'][shipyard.position.x][shipyard.position.y])
    for shipyard in shipyards:
        if state['currentHalite'] > 500 and not state['next'][shipyard.cell.position.x][shipyard.cell.position.y]:
            shipyard.next_action = ShipyardAction.SPAWN   
            state['currentHalite'] -= 500

def convert_tasks():
    global action

    # Add convertion tasks

    rewardMap = shipyard_reward_map() # Best area to build a shipyard
    currentShipyards = state['myShipyards'] # Shipyards "existing"
    targetShipyards = currentShipyards[:]

    t = np.where(rewardMap==np.amax(rewardMap))
    tx,ty = list(zip(t[0], t[1]))[0]

    # Calculate the reward for each cell

    if len(currentShipyards) == 0:
        # Grab the closest ship to the target and build.
        closest  = closest_ship(Point(tx,ty))
        action[closest] = (math.inf,closest,Point(tx,ty))
        targetShipyards.append(state['board'].cells[Point(tx,ty)])
        state['currentHalite'] -= 500
    elif len(state['myShips']) >= len(currentShipyards) * 5:
        targetShipyards.append(state['board'].cells[Point(tx,ty)])
        state['currentHalite'] -= 500

    state['closestShipyard'] = closest_shipyard(targetShipyards)

# General calculations whose values are expected to be used in multiple instances
# Basically calc in botv1.0. 
# Run in update() - see dependency.py

def encode():
    global state
    
    N = state['configuration'].size

    # Halite 
    state['haliteMap'] = np.zeros((N, N))
    for cell in state['cells']:
        state['haliteMap'][cell.position.x][cell.position.y] = cell.halite
    # Halite Spread
    state['haliteSpread'] = np.copy(state['haliteMap'])
    for i in range(3):
        state['haliteSpread'] += np.roll(state['haliteMap'],i,axis=0) / (i+1)
        state['haliteSpread'] += np.roll(state['haliteMap'],-i,axis=0) / (i+1)
    temp = state['haliteSpread'].copy()
    for i in range(3):
        state['haliteSpread'] += np.roll(temp,i,axis=1) / (i+1)
        state['haliteSpread'] += np.roll(temp,-i,axis=1) / (i+1)
    # Ships
    state['shipMap'] = np.zeros((state['playerNum'], N, N))
    for ship in state['ships']:
        state['shipMap'][ship.player_id][ship.position.x][ship.position.y] = 1
    # Shipyards
    state['shipyardMap'] = np.zeros((state['playerNum'], N, N))
    for shipyard in state['shipyards']:
        state['shipyardMap'][shipyard.player_id][shipyard.position.x][shipyard.position.y] = 1
    # Mean Halite 
    state['haliteMean'] = np.mean(state['haliteMap'], axis=None)
    # Friendly units
    state['ally'] = state['shipMap'][state['me']]
    # Friendly shipyards
    state['allyShipyard'] = state['shipyardMap'][state['me']]
    # Enemy units
    state['enemy'] = np.sum(state['shipMap'], axis=0) - state['ally']
    # Enemy shipyards
    state['enemyShipyard'] = np.sum(state['shipyardMap'], axis=0) - state['allyShipyard']
    # Closest shipyard
    state['closestShipyard'] = closest_shipyard(state['myShipyards'])
    # Control map
    state['controlMap'] = control_map(state['ally']-state['enemy'],state['allyShipyard']-state['enemyShipyard'])
    #Enemy ship labeled by halite. If none, infinity
    state['enemyShipHalite'] = np.zeros((N, N))
    state['enemyShipHalite'] += np.Infinity
    for ship in state['ships']:
        if ship.player.id != state['me']:
            state['enemyShipHalite'][ship.position.x][ship.position.y] = ship.halite
    # Avoidance map (Places not to go for each ship)
    for ship in state['myShips']:
        state[ship] = {}
        state[ship]['blocked'] = get_avoidance(ship)

    
def get_avoidance(s):
    threshold = s.halite
    #Enemy units
    temp = np.where(state['enemyShipHalite'] < threshold, 1, 0)
    enemyBlock = np.copy(temp)
    enemyBlock = enemyBlock + np.roll(temp,1,axis=0)
    enemyBlock = enemyBlock + np.roll(temp,-1,axis=0)
    enemyBlock = enemyBlock + np.roll(temp,1,axis=1)
    enemyBlock = enemyBlock + np.roll(temp,-1,axis=1)

    enemyBlock = enemyBlock + state['enemyShipyard'] - state['allyShipyard']*5

    blocked = enemyBlock
    blocked = np.where(blocked>0,1,0)
    return blocked

def closest_shipyard(shipyards):
    N = state['configuration'].size
    res = [[None for y in range(N)]for x in range(N)]
    for x in range(N):
        for y in range(N):
            minimum = math.inf
            for shipyard in shipyards:
                if dist(Point(x,y),shipyard.position) < minimum:
                    minimum = dist(Point(x,y),shipyard.position)
                    res[x][y] = shipyard.position
    return res
    

def control_map(ships,shipyards):
        
        ITERATIONS = 4
        
        res = ships

        #TODO: Use convolutions instead of this hacky method.
        # Convolutions will be more extensible down the line

        for i in range(ITERATIONS):
            temp = np.roll(res,1,axis=0)
            temp += np.roll(res,-1,axis=0)
            temp += np.roll(res,1,axis=1)
            temp += np.roll(res,-1,axis=1)

            res += temp
        
        return res + shipyards

# Direction from point s to point t
def direction_to(s: Point, t: Point) -> ShipAction:
    candidate = directions_to(s, t)
    return random.choice(candidate) if len(candidate) > 0 else None

# Distance from point a to b
def dist(a: Point, b: Point) -> int:
    N = state['configuration'].size
    return min(abs(a.x - b.x), N - abs(a.x - b.x)) + min(abs(a.y - b.y), N - abs(a.y - b.y))

# Returns list of possible directions
def directions_to(s: Point, t: Point) -> ShipAction:
    N = state['configuration'].size
    candidates = [] # [N/S, E/W]
    if s.x-t.x != 0:
        candidates.append(ShipAction.WEST if (s.x-t.x) % N < (t.x-s.x) % N else ShipAction.EAST)
    if s.y-t.y != 0:
        candidates.append(ShipAction.SOUTH if (s.y-t.y) % N < (t.y-s.y) % N else ShipAction.NORTH)
    return candidates

# Deserialize an integer which represents a point
def unpack(n):
    N = state['configuration'].size
    return Point(n // N, n % N)

# A default direction to target
def direction_to(s: Point, t: Point) -> ShipAction:
    candidate = directions_to(s, t)
    return random.choice(candidate) if len(candidate) > 0 else None


# Returns the "next" point of a ship at point s with shipAction d
def dry_move(s: Point, d: ShipAction) -> Point:
    N = state['configuration'].size
    if d == ShipAction.NORTH:
        return s + Point(0, 1) % N
    elif d == ShipAction.SOUTH:
        return s + Point(0, -1) % N
    elif d == ShipAction.EAST:
        return s + Point(1, 0) % N
    elif d == ShipAction.WEST:
        return s + Point(-1, 0) % N
    else:
        return s
    
# Returns list of len 4 of adjacent points to a point
def get_adjacent(point):
    N = state['configuration'].size
    res = []
    for offX, offY in ((0,1),(1,0),(0,-1),(-1,0)):
        res.append(point.translate(Point(offX,offY),N))
    return res

# A* Movement from ship s to point t
# See https://en.wikipedia.org/wiki/A*_search_algorithm
def a_move(s : Ship, t : Point, inBlocked):

    nextMap = state['next']
    sPos = s.position
    blocked = inBlocked + nextMap
    blocked = np.where(blocked>0,1,0)

    #Stay still
    if sPos == t:
        #Someone with higher priority needs position, must move. Or being attacked.
        if blocked[t.x][t.y]:
            for processPoint in get_adjacent(sPos):
                if not blocked[processPoint.x][processPoint.y]:
                    nextMap[processPoint.x][processPoint.y] = 1
                    return direction_to(sPos,processPoint)
            nextMap[sPos.x][sPos.y] = 1
            return None
        else:
            nextMap[sPos.x][sPos.y] = 1
            return None

    #A*
    pred = {}
    calcDist = {}
    pq = PriorityQueue()
    pqMap = {}

    pqMap[dist(sPos,t)] = [sPos]
    pq.put(dist(sPos,t))
    pred[sPos] = sPos
    calcDist[sPos] = dist(sPos,t)

        # Main

    while not pq.empty():
        if t in calcDist:
            break
        currentPoint = pqMap.get(pq.get()).pop()
        for processPoint in get_adjacent(currentPoint):
            if blocked[processPoint.x][processPoint.y] or processPoint in calcDist: 
                continue
            calcDist[processPoint] = calcDist[currentPoint] + 1
            priority =  calcDist[processPoint] + dist(processPoint,t)
            pqMap[priority] = pqMap.get(priority,[])
            pqMap[priority].append(processPoint)
            pq.put(priority)
            pred[processPoint] = currentPoint

    if not t in pred:
        #Random move
        for processPoint in get_adjacent(sPos):
            if not blocked[processPoint.x][processPoint.y]:
                nextMap[processPoint.x][processPoint.y] = 1
                return direction_to(sPos,processPoint)
        nextMap[sPos.x][sPos.y] = 1
        return None

        # Path reconstruction
    while pred[t] != sPos:
        t = pred[t]

    desired = direction_to(sPos,t)
    nextMap[t.x][t.y] = 1
    
    return desired
# Key function
# For a ship, return the inherent "value" of the ship to get to a target cell
# This should take the form of a neural network
def get_reward(ship,cell):
    return optimus_reward(ship,cell)

def optimus_reward(ship,cell):
    reward = 0
    INF = int(1e9)
    me = state['board'].current_player
    if (cell.ship is None or cell.ship is ship) and cell.shipyard is None: # mineral
        d1 = dist(ship.position, cell.position)
        d2 = dist(cell.position, state['closestShipyard'][cell.position.x][cell.position.y]) # TODO: edge case no shipyards
        reward = halite_per_turn(ship.halite, cell.halite, d1 + d2)
    elif cell.ship is not None and cell.ship.player.is_current_player: # friendly ship
        reward = -INF # avoid clustering
    elif cell.ship is not None and not cell.ship.player.is_current_player: # enemy ship
        dist_ = dist(ship.position, cell.position)
        reward = cell.ship.halite / (dist_ * CHASE_PUNISHMENT) if cell.ship.halite > me.halite and dist_ <= MAX_CHASE_RANGE else 0 # TUNABLE
    elif cell.shipyard is not None and cell.shipyard.player.is_current_player: # friendly shipyard
        reward = ship.halite / max(dist(ship.position, cell.position), 0.1) # TODO: TUNABLE?
    elif cell.shipyard is not None and not cell.shipyard.player.is_current_player: # enemy shipyard
        reward = SHIPYARD_DEMOLISH_REWARD / dist(ship.position, cell.position)
    return reward

def naive_reward(ship,cell):
    # For testing purposes
    if cell.ship != None and cell.ship.player_id != state['me'] and cell.ship.halite < ship.halite:
        return -100
    else:
        res = cell.halite - dist(ship.position,cell.position) * 10
        if cell.ship == ship:
            res += 50
        return res

# Returns the reward of converting a shipyard in the area, relative.
# TODO: Convert to absolute instead of relative

def shipyard_reward_map():

    N = state['configuration'].size

    closestShipyard = closestShipyard = np.zeros((N,N))
    if len(state['myShipyards']) != 0:
        closestShipyardPosition = state['closestShipyard']
        for x in range(N):
            for y in range(N):
                closestShipyard[x][y] = dist(Point(x,y),closestShipyardPosition[x][y])

    closestShipyard = normalize(closestShipyard.flatten())
    haliteSpread = normalize(state['haliteSpread'].flatten())
    halite = normalize(state['haliteMap'].flatten())
    control = normalize(state['controlMap'].flatten())
    controlAlly = control.copy()
    controlAlly[controlAlly<0] = 0
    controlOpponent = control.copy()
    controlOpponent[controlOpponent>0] = 0

    tensorIn = np.array([closestShipyard,haliteSpread,halite,controlOpponent,controlAlly]).T

    # Linear calculation
    # TODO: Improve by converting to a deep NN
    tensorOut = tensorIn @ weights[0]
    res = np.reshape(tensorOut,(N,N))

    return res



        

# The final function

@board_agent
def agent(board):

    print("Turn =",board.step+1)
    # Init
    if board.step == 0:
        init(board)

    # Update
    update(board)
    
    # Convert
    convert_tasks()
    
    # Ship
    ship_tasks()
    
    # Spawn
    spawn_tasks()