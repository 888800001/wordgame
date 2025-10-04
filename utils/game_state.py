class GameState:
    def __init__(self):
        self.turn_index = 0
        self.active_rule = None
        self.in_duel = False
        self.last_action = None
        self.winner = None
