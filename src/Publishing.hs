{-# LANGUAGE OverloadedStrings #-}
-- Site-wide publishing views. Notes and reviews retain their own source rules.
module Publishing where

import Data.Aeson (Value)
import Data.List (isPrefixOf, sortOn)
import qualified Data.Map.Strict as M
import Hakyll
import qualified View as V

-- A body is rendered Markdown only. A feed entry may add content metadata,
-- but never section navigation or the standalone page wrapper.
bodySnapshot, feedSnapshot :: Snapshot
bodySnapshot = "body"
feedSnapshot = "feed"

notesPattern :: Pattern
notesPattern = "posts/*/index.md" .&&. hasNoVersion

type TagIndex = M.Map Identifier [String]

loadPostTags :: [Identifier] -> IO TagIndex
loadPostTags sources = M.fromList <$> mapM loadTags (sortOn toFilePath sources)
  where loadTags source = do
          meta <- V.readDocument $ toFilePath source
          tags <- either (fail . ((toFilePath source ++ ": ") ++)) pure $ V.normalTags $ V.get "tags" meta
          pure (source,tags)

postTagUrl :: String -> String
postTagUrl = V.tagUrlIn "/tags/"

tagGroups :: TagIndex -> [(String, [Identifier])]
tagGroups index = M.elems $ M.fromListWith merge
  [(V.foldCase label,(label,[source])) | (source,labels) <- M.toAscList index, label <- labels]
  where merge (_,new) (label,old) = (label,old ++ new)

tagLinks :: TagIndex -> Identifier -> Value
tagLinks index source = V.values
  [V.obj [("name",V.val label),("url",V.val $ postTagUrl label)]
  | label <- M.findWithDefault [] source index]

postCtx :: TagIndex -> Context String
postCtx tags = dateField "date" "%Y-%m-%d" <> Context tagContext <> defaultContext
  where tagContext key args item
          | key == "postTags" = unContext (V.viewContext $ V.obj [("postTags",tagLinks tags $ itemIdentifier item)]) key args item
          | otherwise = noResult $ "No post field " ++ key

siteFields, siteCtx :: Context String
siteFields = constField "siteTitle" "t0mb.net" <> constField "siteDescription" "Brain spill"
siteCtx = siteFields <> defaultContext

page :: Identifier -> Context String -> Item String -> Compiler (Item String)
page template context item = loadAndApplyTemplate template context item
  >>= loadAndApplyTemplate "templates/default.html" context >>= relativizeUrls

publishingRules :: Pattern -> TagIndex -> Context String -> Rules ()
publishingRules writing tags featuredReviews = do
  create ["index.html"] $ do
    route idRoute
    compile $ do
      posts <- fmap (take 3) . recentFirst =<< loadAllSnapshots notesPattern bodySnapshot
      intro <- loadBody "content/home.md"
      introTitle <- getMetadataField' "content/home.md" "title"
      let context = listField "posts" (postCtx tags) (pure posts)
            <> boolField "hasPosts" (const $ not $ null posts)
            <> constField "intro" intro <> constField "introTitle" (escapeHtml introTitle)
            <> constField "title" "Home" <> featuredReviews <> siteCtx
      makeItem "" >>= page "templates/home.html" context
  create ["notes/index.html"] $ do
    route idRoute
    compile $ do
      posts <- recentFirst =<< loadAllSnapshots notesPattern bodySnapshot
      let context = listField "posts" (postCtx tags) (pure posts) <> constField "title" "Notes" <> siteCtx
      makeItem "" >>= page "templates/notes.html" context
  create ["archive.html"] $ do
    route idRoute
    compile $ do
      posts <- recentFirst =<< loadAllSnapshots writing bodySnapshot
      let context = listField "posts" (postCtx tags) (pure posts) <> constField "title" "Writing archive" <> siteCtx
      makeItem "" >>= page "templates/archive.html" context
  create ["rss.xml"] $ do
    route idRoute
    compile $ do
      posts <- fmap (take 20) . recentFirst =<< loadAllSnapshots writing feedSnapshot
      let absolute url = if "/" `isPrefixOf` url && not ("//" `isPrefixOf` url) then "https://t0mb.net" ++ url else url
      renderRss feedConfig (postCtx tags <> bodyField "description") (map (fmap $ withUrls absolute) posts)
  create ["tags/index.html"] $ do
    route idRoute
    compile $ do
      let links = V.values [V.obj [("name",V.val label),("url",V.val $ postTagUrl label),("count",V.number $ length sources)] | (label,sources) <- tagGroups tags]
          context = V.viewContext (V.obj [("postTags",links)]) <> constField "title" "Post tags" <> siteCtx
      makeItem "" >>= page "templates/tags.html" context
  let labels = M.fromList [(V.foldCase label,label) | (label,_) <- tagGroups tags]
  builtTags <- buildTagsWith
    (\source -> pure [labels M.! V.foldCase label | label <- M.findWithDefault [] source tags])
    writing (fromFilePath . V.routePath . postTagUrl)
  tagsRules builtTags tagPage
  where
    tagPage label pattern = do
      route idRoute
      compile $ do
        posts <- recentFirst =<< loadAllSnapshots (pattern .&&. hasNoVersion) bodySnapshot
        let context = listField "posts" (postCtx tags) (pure posts)
              <> constField "title" (escapeHtml $ "Posts tagged “" ++ label ++ "”") <> siteCtx
        makeItem "" >>= page "templates/tag.html" context

feedConfig :: FeedConfiguration
feedConfig = FeedConfiguration "t0mb.net" "Brain spill" "Tom Boland" "" "https://t0mb.net"
