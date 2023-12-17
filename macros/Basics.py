import time

class Level:
    def __init__(self,maxage,lvaluetype, l_logger):
         self.maxage=maxage
         self.distinctValues = dict()
         self.valuetype = lvaluetype
         self.logger = l_logger
                 
    def __str__(self):
        return f"{self.distinctValues}"
    
    def addLevel(self,lvalue):
        ltime=time.time()
        self.logger.debug("Adding at %d %s Value: %s" ,int(ltime),self.valuetype ,str(lvalue))
        self.distinctValues[str(int(ltime))]=lvalue
        #delete all values older than maxage
        cleanedValues = dict()
        for x in self.distinctValues:
            if (int(ltime) - int(x) <= self.maxage ):
                cleanedValues[str(x)]=self.distinctValues[str(x)]
            else:
                self.logger.debug("throwing away old %s value %d",self.valuetype, int(x))
        self.distinctValues=cleanedValues.copy()
    
    def getAverageValues(self):
        list_values = list(self.distinctValues.values())
        self.logger.debug ("Current %s average is: %d", self.valuetype, sum(list_values) / len(list_values) )
        return sum(list_values) / len(list_values)
    
    def isStable(self):
        same = True
        enough = True
        # extracting value to compare
        test_val = list(self.distinctValues.values())[0]
         
        for ele in self.distinctValues:
            if self.distinctValues[ele] != test_val:
                same = False
                break
         
        # printing result
        self.logger.debug("All  %s values recorded are identical: %s",self.valuetype, str(same))
        
        if (len(list(self.distinctValues.values())) >=self.maxage/10): #10% der Zeitreihe muss gefüllt sein um aussagekräftig zu sein.
            enough = True
            self.logger.debug("Enough  %s values provided: %d", self.valuetype, len(list(self.distinctValues.values())) )
        else:
            enough = False
            self.logger.debug("Insufficient  %s values provided: %d", self.valuetype, len(list(self.distinctValues.values())) )
        if same and enough:
            return True
        else:
            return False


