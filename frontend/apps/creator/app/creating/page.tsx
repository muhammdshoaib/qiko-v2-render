"use client";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Shield, Brain, Rocket, Check, Cpu, Database, Network, Zap } from "lucide-react";
import { useState, useEffect, useRef, useCallback } from "react";
import { useLocation, useParams } from "@/lib/wouter";
import Confetti from "@/components/Confetti";

const STAGES = [
  {
    id: 1,
    title: "Initializing neural architecture",
    description: "Building your AI's cognitive framework",
    icon: Cpu,
    duration: 1000,
    color: "#6366F1",
  },
  {
    id: 2,
    title: "Securing data pathways",
    description: "Encrypting your private AI workspace",
    icon: Shield,
    duration: 2000,
    color: "#22D3EE",
  },
  {
    id: 3,
    title: "Loading knowledge modules",
    description: "Integrating your expertise into the model",
    icon: Database,
    duration: 500,
    color: "#A855F7",
  },
  {
    id: 4,
    title: "Training response patterns",
    description: "Calibrating for your communication style",
    icon: Brain,
    duration: 500,
    color: "#10B981",
  },
  {
    id: 5,
    title: "Activating neural connections",
    description: "Your AI worker is coming online",
    icon: Network,
    duration: 1000,
    color: "#F59E0B",
  },
];

// Neural network node component
function NeuralNode({ x, y, delay, active }: { x: number; y: number; delay: number; active: boolean }) {
  return (
    <motion.div
      className="absolute w-2 h-2 rounded-full"
      style={{ left: `${x}%`, top: `${y}%` }}
      initial={{ scale: 0, opacity: 0 }}
      animate={{ 
        scale: active ? [1, 1.5, 1] : 1, 
        opacity: active ? [0.3, 1, 0.3] : 0.2,
        boxShadow: active ? '0 0 20px rgba(99, 102, 241, 0.8)' : 'none'
      }}
      transition={{ 
        delay, 
        duration: 2,
        repeat: Infinity,
        repeatType: "reverse"
      }}
    >
      <div className={`w-full h-full rounded-full ${active ? 'bg-[#22D3EE]' : 'bg-white/30'}`} />
    </motion.div>
  );
}

// Data stream particle
function DataParticle({ delay }: { delay: number }) {
  const startX = Math.random() * 100;
  const endX = startX + (Math.random() - 0.5) * 30;
  
  return (
    <motion.div
      className="absolute w-1 h-1 bg-[#22D3EE] rounded-full"
      style={{ left: `${startX}%` }}
      initial={{ top: "100%", opacity: 0 }}
      animate={{ 
        top: "-5%", 
        left: `${endX}%`,
        opacity: [0, 1, 1, 0] 
      }}
      transition={{ 
        delay,
        duration: 3,
        repeat: Infinity,
        ease: "linear"
      }}
    />
  );
}

// Floating code snippet
function CodeSnippet({ text, x, y, delay }: { text: string; x: number; y: number; delay: number }) {
  return (
    <motion.div
      className="absolute text-[10px] font-mono text-[#6366F1]/40 whitespace-nowrap"
      style={{ left: `${x}%`, top: `${y}%` }}
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: [0, 0.6, 0], x: 20 }}
      transition={{ delay, duration: 4, repeat: Infinity }}
    >
      {text}
    </motion.div>
  );
}

// Central AI orb
function AIOrb({ stage, isComplete }: { stage: number; isComplete: boolean }) {
  const colors = STAGES.map(s => s.color);
  const currentColor = isComplete ? "#22D3EE" : colors[Math.min(stage, colors.length - 1)];
  
  return (
    <div className="relative w-40 h-40 mx-auto">
      {/* Outer glow rings */}
      <motion.div
        className="absolute inset-0 rounded-full"
        style={{
          background: `radial-gradient(circle, ${currentColor}20 0%, transparent 70%)`,
        }}
        animate={{ 
          scale: [1, 1.3, 1],
          opacity: [0.5, 0.8, 0.5]
        }}
        transition={{ duration: 2, repeat: Infinity }}
      />
      
      {/* Rotating ring */}
      <motion.div
        className="absolute inset-2 rounded-full border-2 border-dashed"
        style={{ borderColor: `${currentColor}40` }}
        animate={{ rotate: 360 }}
        transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
      />
      
      {/* Inner rotating ring */}
      <motion.div
        className="absolute inset-6 rounded-full border"
        style={{ borderColor: `${currentColor}60` }}
        animate={{ rotate: -360 }}
        transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
      />
      
      {/* Core orb */}
      <motion.div
        className="absolute inset-8 rounded-full flex items-center justify-center overflow-hidden"
        style={{
          background: isComplete 
            ? `linear-gradient(135deg, #22D3EE 0%, #6366F1 100%)`
            : `linear-gradient(135deg, ${currentColor} 0%, ${currentColor}80 100%)`,
          boxShadow: `0 0 60px ${currentColor}80, inset 0 0 30px rgba(255,255,255,0.2)`
        }}
        animate={isComplete ? { scale: [1, 1.1, 1] } : { scale: 1 }}
        transition={{ duration: 0.5 }}
      >
        <AnimatePresence mode="wait">
          {isComplete ? (
            <motion.div
              key="complete"
              initial={{ scale: 0, rotate: -180 }}
              animate={{ scale: 1, rotate: 0 }}
              exit={{ scale: 0 }}
              transition={{ type: "spring", stiffness: 200 }}
            >
              <Check className="w-12 h-12 text-white" strokeWidth={3} />
            </motion.div>
          ) : (
            <motion.div
              key={stage}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              {stage < STAGES.length ? (
                (() => {
                  const StageIcon = STAGES[stage].icon;
                  return <StageIcon className="w-10 h-10 text-white" />;
                })()
              ) : (
                <Zap className="w-10 h-10 text-white" />
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
      
      {/* Orbiting particles */}
      {[0, 1, 2, 3].map((i) => (
        <motion.div
          key={i}
          className="absolute w-2 h-2 rounded-full"
          style={{
            background: currentColor,
            boxShadow: `0 0 10px ${currentColor}`,
            top: "50%",
            left: "50%",
          }}
          animate={{
            x: [
              Math.cos((i * Math.PI) / 2) * 70,
              Math.cos((i * Math.PI) / 2 + Math.PI) * 70,
              Math.cos((i * Math.PI) / 2) * 70,
            ],
            y: [
              Math.sin((i * Math.PI) / 2) * 70,
              Math.sin((i * Math.PI) / 2 + Math.PI) * 70,
              Math.sin((i * Math.PI) / 2) * 70,
            ],
          }}
          transition={{
            duration: 4,
            repeat: Infinity,
            delay: i * 0.5,
            ease: "linear",
          }}
        />
      ))}
    </div>
  );
}

// Progress bar with glow
function ProgressBar({ progress, color }: { progress: number; color: string }) {
  return (
    <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
      <motion.div
        className="h-full rounded-full"
        style={{
          background: `linear-gradient(90deg, ${color}, ${color}80)`,
          boxShadow: `0 0 20px ${color}80`,
        }}
        initial={{ width: 0 }}
        animate={{ width: `${progress}%` }}
        transition={{ duration: 0.5 }}
      />
    </div>
  );
}

export default function CreatingWorker() {
  const [, setLocation] = useLocation();
  const params = useParams<{ workerId?: string }>();
  const workerId = params.workerId ? parseInt(params.workerId, 10) : undefined;
  const [currentStage, setCurrentStage] = useState(0);
  const [stageProgress, setStageProgress] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [showConfetti, setShowConfetti] = useState(false);
  const [totalProgress, setTotalProgress] = useState(0);

  // Generate neural network nodes
  const neuralNodes = useRef(
    Array.from({ length: 30 }, () => ({
      x: Math.random() * 100,
      y: Math.random() * 100,
      delay: Math.random() * 2,
    }))
  ).current;

  // Generate data particles
  const dataParticles = useRef(
    Array.from({ length: 20 }, (_, i) => ({
      delay: i * 0.3,
    }))
  ).current;

  // Code snippets
  const codeSnippets = [
    "model.initialize()",
    "await loadWeights()",
    "neural.connect()",
    "encrypt(data)",
    "train(expertise)",
    "calibrate(tone)",
    "activate(worker)",
  ];

  useEffect(() => {
    let timeout: NodeJS.Timeout;
    let progressInterval: NodeJS.Timeout;

    if (currentStage < STAGES.length) {
      const stageDuration = STAGES[currentStage].duration;
      
      // Animate progress within stage
      setStageProgress(0);
      const progressStep = 100 / (stageDuration / 50);
      progressInterval = setInterval(() => {
        setStageProgress(prev => Math.min(prev + progressStep, 100));
      }, 50);

      timeout = setTimeout(() => {
        setCurrentStage(prev => prev + 1);
        setTotalProgress(((currentStage + 1) / STAGES.length) * 100);
      }, stageDuration);
    } else if (currentStage === STAGES.length && !isComplete) {
      setTimeout(() => {
        setIsComplete(true);
        setShowConfetti(true);
        setTotalProgress(100);
      }, 500);
    }

    return () => {
      clearTimeout(timeout);
      clearInterval(progressInterval);
    };
  }, [currentStage, isComplete]);

  const currentColor = currentStage < STAGES.length ? STAGES[currentStage].color : "#22D3EE";

  return (
    <div className="min-h-screen bg-[#050810] flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Animated background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        {/* Large gradient orbs */}
        <motion.div 
          className="absolute w-[800px] h-[800px] rounded-full opacity-20"
          style={{
            background: `radial-gradient(circle, ${currentColor} 0%, transparent 70%)`,
            top: '-20%',
            left: '-10%',
            filter: 'blur(100px)',
          }}
          animate={{ 
            scale: [1, 1.2, 1],
            x: [0, 50, 0],
            y: [0, 30, 0],
          }}
          transition={{ duration: 8, repeat: Infinity }}
        />
        <motion.div 
          className="absolute w-[600px] h-[600px] rounded-full opacity-15"
          style={{
            background: 'radial-gradient(circle, #22D3EE 0%, transparent 70%)',
            bottom: '-10%',
            right: '-5%',
            filter: 'blur(80px)',
          }}
          animate={{ 
            scale: [1, 1.3, 1],
            x: [0, -30, 0],
          }}
          transition={{ duration: 10, repeat: Infinity }}
        />

        {/* Grid overlay */}
        <div 
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(rgba(99, 102, 241, 0.5) 1px, transparent 1px),
              linear-gradient(90deg, rgba(99, 102, 241, 0.5) 1px, transparent 1px)
            `,
            backgroundSize: '50px 50px',
          }}
        />

        {/* Neural network nodes */}
        {neuralNodes.map((node, i) => (
          <NeuralNode 
            key={i} 
            x={node.x} 
            y={node.y} 
            delay={node.delay}
            active={!isComplete && Math.random() > 0.5}
          />
        ))}

        {/* Data stream particles */}
        {!isComplete && dataParticles.map((particle, i) => (
          <DataParticle key={i} delay={particle.delay} />
        ))}

        {/* Floating code snippets */}
        {codeSnippets.map((snippet, i) => (
          <CodeSnippet 
            key={i}
            text={snippet}
            x={10 + (i * 12)}
            y={20 + (i * 10)}
            delay={i * 0.8}
          />
        ))}
      </div>

      {/* Confetti */}
      {showConfetti && <Confetti />}

      <div className="relative z-10 max-w-xl w-full text-center">
        {/* AI Orb */}
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5 }}
          className="mb-8"
        >
          <AIOrb stage={currentStage} isComplete={isComplete} />
        </motion.div>

        {/* Title */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="text-3xl lg:text-4xl font-bold mb-3"
          style={{
            fontFamily: 'Satoshi, sans-serif',
            background: isComplete 
              ? 'linear-gradient(135deg, #22D3EE 0%, #6366F1 100%)'
              : `linear-gradient(135deg, #ffffff 0%, ${currentColor} 100%)`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          {isComplete ? "Your AI worker is online!" : "Building your AI worker"}
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="text-white/60 mb-8 text-lg"
        >
          {isComplete
            ? "Neural networks activated. Your digital expert is ready to serve."
            : "Configuring neural pathways and loading your expertise..."}
        </motion.p>

        {/* Overall progress */}
        <div className="mb-8">
          <div className="flex justify-between text-sm text-white/40 mb-2">
            <span>System initialization</span>
            <span>{Math.round(totalProgress)}%</span>
          </div>
          <ProgressBar progress={totalProgress} color={currentColor} />
        </div>

        {/* Progress Stages */}
        <div className="space-y-3 mb-10">
          {STAGES.map((stage, index) => {
            const StageIcon = stage.icon;
            const isActive = index === currentStage;
            const isCompleted = index < currentStage;

            return (
              <motion.div
                key={stage.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 + index * 0.1 }}
                className={`flex items-center gap-4 p-4 rounded-xl border backdrop-blur-sm transition-all duration-300 ${
                  isCompleted
                    ? "bg-white/5 border-white/10"
                    : isActive
                    ? "bg-white/10 border-white/20"
                    : "bg-white/[0.02] border-white/5"
                }`}
                style={{
                  boxShadow: isActive ? `0 0 30px ${stage.color}20` : 'none',
                }}
              >
                <div
                  className="w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-300"
                  style={{
                    background: isCompleted || isActive 
                      ? `linear-gradient(135deg, ${stage.color} 0%, ${stage.color}80 100%)`
                      : 'rgba(255,255,255,0.1)',
                    boxShadow: isActive ? `0 0 20px ${stage.color}60` : 'none',
                  }}
                >
                  {isCompleted ? (
                    <Check className="w-5 h-5 text-white" />
                  ) : (
                    <StageIcon className={`w-5 h-5 ${isCompleted || isActive ? 'text-white' : 'text-white/40'}`} />
                  )}
                </div>
                <div className="flex-1 text-left">
                  <p className={`font-medium ${isCompleted || isActive ? "text-white" : "text-white/40"}`}>
                    {stage.title}
                  </p>
                  <p className="text-sm text-white/40">{stage.description}</p>
                  {isActive && (
                    <div className="mt-2">
                      <ProgressBar progress={stageProgress} color={stage.color} />
                    </div>
                  )}
                </div>
                {isActive && !isCompleted && (
                  <motion.div 
                    className="w-6 h-6 rounded-full border-2 border-t-transparent"
                    style={{ borderColor: stage.color }}
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                  />
                )}
              </motion.div>
            );
          })}
        </div>

        {/* CTA Button */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: isComplete ? 1 : 0.3, y: 0 }}
          transition={{ delay: 0.7 }}
        >
          <Button
            size="lg"
            className="w-full sm:w-auto px-10 py-6 text-lg font-semibold rounded-xl transition-all duration-300"
            style={{
              background: isComplete 
                ? 'linear-gradient(135deg, #6366F1 0%, #22D3EE 100%)'
                : 'rgba(255,255,255,0.1)',
              boxShadow: isComplete ? '0 0 40px rgba(99, 102, 241, 0.5)' : 'none',
            }}
            disabled={!isComplete}
            onClick={() => setLocation(workerId ? `/workers/${workerId}` : "/dashboard")}
          >
            <Sparkles className="w-5 h-5 mr-2" />
            Enter Dashboard
          </Button>
        </motion.div>

        {/* Status text */}
        {!isComplete && currentStage < STAGES.length && (
          <motion.p
            key={currentStage}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-6 text-sm text-white/30 font-mono"
          >
            {`> ${STAGES[currentStage].title.toLowerCase()}...`}
          </motion.p>
        )}
      </div>
    </div>
  );
}
